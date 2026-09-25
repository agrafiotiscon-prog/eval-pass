"""Bid/ask-accurate backtest engine.

Signals are computed on a signal grid (usually M1); execution is simulated on a finer
grid (10-second bid/ask bars). An intent produced at the close of signal bar i becomes
active on the first execution bar of signal bar i+1, so there is no look-ahead.

Conventions (match MT5):
  * buy fills at Ask, sell fills at Bid
  * buy-stop triggers when Ask >= level, sell-stop when Bid <= level
  * long SL/TP are hit by Bid, short SL/TP by Ask
  * if SL and TP are both inside one execution bar, SL is assumed first
"""
import glob

import numba as nb
import numpy as np
import pandas as pd

DATA_DIR = "/tmp/data"

# exit reason codes
X_SL, X_TP, X_MOVED_SL, X_SIGNAL, X_TIME = 1, 2, 3, 4, 5


def load_bars(sym: str, res: str = "s10", start=None, end=None) -> pd.DataFrame:
    files = sorted(glob.glob(f"{DATA_DIR}/{res}/{sym}-*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if start is not None:
        df = df[df.time >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.time < pd.Timestamp(end)]
    return df.reset_index(drop=True)


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.set_index("time").resample(rule, label="left", closed="left")
    out = pd.DataFrame({
        "bo": g.bo.first(), "bh": g.bh.max(), "bl": g.bl.min(), "bc": g.bc.last(),
        "ao": g.ao.first(), "ah": g.ah.max(), "al": g.al.min(), "ac": g.ac.last(),
        "n": g.n.sum(), "spr": g.spr.mean(), "sprmax": g.sprmax.max(),
    }).dropna(subset=["bo"])
    return out.reset_index()


def add_clock(df: pd.DataFrame) -> pd.DataFrame:
    """Add local-session clocks (DST aware) used by session-based rules."""
    t = pd.DatetimeIndex(df.time).tz_localize("UTC")
    ny = t.tz_convert("America/New_York")
    ldn = t.tz_convert("Europe/London")
    df = df.copy()
    df["ny_min"] = (ny.hour * 60 + ny.minute).astype(np.int32)
    df["ldn_min"] = (ldn.hour * 60 + ldn.minute).astype(np.int32)
    df["utc_min"] = (t.hour * 60 + t.minute).astype(np.int32)
    # trading day rolls at 17:00 New York (standard FX / CFD day)
    fx_day = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    df["day"] = fx_day.values.astype("datetime64[D]").astype(np.int64).astype(np.int32)
    df["ny_date"] = ny.normalize().tz_localize(None).values.astype("datetime64[D]").astype(np.int64).astype(np.int32)
    df["dow"] = ny.dayofweek.astype(np.int8)
    return df


class Market:
    """Signal-grid bars plus the matching execution-grid bars."""

    def __init__(self, sym: str, sig_rule: str = "1min", start=None, end=None, exec_res: str = "s10"):
        self.sym = sym
        ex = load_bars(sym, exec_res, start, end)
        sig = resample(ex, sig_rule) if sig_rule != "10s" else ex.copy()
        self.sig = add_clock(sig)
        self.ex = ex
        sig_t = self.sig.time.values
        ex_t = ex.time.values
        self.x2s = (np.searchsorted(sig_t, ex_t, side="right") - 1).astype(np.int64)
        self.first = np.r_[True, self.x2s[1:] != self.x2s[:-1]]
        self.ex_sec = (ex_t.astype("datetime64[s]").astype(np.int64))
        self.ex_arrays = tuple(ex[c].values.astype(np.float64) for c in ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"])

    def intents(self):
        n = len(self.sig)
        return Intents(n)


class Intents:
    def __init__(self, n: int):
        self.ent = np.zeros(n, np.int8)       # 1 buy mkt, -1 sell mkt, 2 buy stop, -2 sell stop, 3 both stops (OCO)
        self.lvl_buy = np.full(n, np.nan)
        self.lvl_sell = np.full(n, np.nan)
        self.sl = np.full(n, np.nan)          # stop distance (price)
        self.tp = np.zeros(n)                 # target distance (price), 0 = none
        self.ex = np.zeros(n, np.int8)        # 1 close long, -1 close short, 2 close all


@nb.njit(cache=True)
def _engine(bo, bh, bl, bc, ao, ah, al, ac, ex_sec, x2s, first, day,
            ent, lvl_buy, lvl_sell, sl_d, tp_d, exs,
            be_trig, be_off, tr_trig, tr_dist, part_r, part_frac,
            max_hold, comm, slip, max_per_day, entry_same_bar_check):
    n = len(bo)
    cap = 400000
    t_in = np.empty(cap, np.int64); t_out = np.empty(cap, np.int64)
    t_dir = np.empty(cap, np.int8); t_px_in = np.empty(cap); t_px_out = np.empty(cap)
    t_r = np.empty(cap); t_pnl = np.empty(cap); t_reason = np.empty(cap, np.int8)
    t_mfe = np.empty(cap); t_mae = np.empty(cap)
    nt = 0

    pos = 0
    e_px = 0.0; sl = 0.0; tp = 0.0; R = 0.0; k_in = 0
    best = 0.0; worst = 0.0; part_done = False; part_px = 0.0; moved = False
    cur_day = -1; day_count = 0
    pend_b = np.nan; pend_s = np.nan; pend_sl = 0.0; pend_tp = 0.0; pend_mkt = 0

    for k in range(n):
        i = x2s[k]
        closed_now = False
        if first[k] and i >= 1:
            j = i - 1
            if day[i] != cur_day:
                cur_day = day[i]; day_count = 0
            # exit signals from completed signal bar j
            if pos != 0 and (exs[j] == 2 or exs[j] == pos):
                px = bo[k] - slip if pos == 1 else ao[k] + slip
                reason = X_SIGNAL
                # fall through to close below
                pnl = (px - e_px) * pos
                if part_done:
                    pnl = part_frac * (part_px - e_px) * pos + (1 - part_frac) * pnl
                pnl -= 2 * comm
                t_in[nt] = k_in; t_out[nt] = k; t_dir[nt] = pos; t_px_in[nt] = e_px; t_px_out[nt] = px
                t_pnl[nt] = pnl; t_r[nt] = pnl / R; t_reason[nt] = reason
                t_mfe[nt] = best / R; t_mae[nt] = worst / R
                nt += 1; pos = 0; closed_now = True
            # new orders
            pend_b = np.nan; pend_s = np.nan; pend_mkt = 0
            if pos == 0 and ent[j] != 0 and day_count < max_per_day and nt < cap - 1:
                pend_sl = sl_d[j]; pend_tp = tp_d[j]
                if ent[j] == 1 or ent[j] == -1:
                    pend_mkt = ent[j]
                if ent[j] == 2 or ent[j] == 3:
                    pend_b = lvl_buy[j]
                if ent[j] == -2 or ent[j] == 3:
                    pend_s = lvl_sell[j]

        # --- entries ---
        if pos == 0 and not closed_now:
            filled = 0; fpx = 0.0
            if pend_mkt != 0:
                if pend_mkt == 1:
                    filled = 1; fpx = ao[k] + slip
                else:
                    filled = -1; fpx = bo[k] - slip
                pend_mkt = 0
            else:
                hit_b = (not np.isnan(pend_b)) and ah[k] >= pend_b
                hit_s = (not np.isnan(pend_s)) and bl[k] <= pend_s
                if hit_b and hit_s:
                    # both sides touched inside one bar: take the side nearer the open
                    if abs(pend_b - ao[k]) <= abs(bo[k] - pend_s):
                        hit_s = False
                    else:
                        hit_b = False
                if hit_b:
                    filled = 1; fpx = max(pend_b, ao[k]) + slip
                elif hit_s:
                    filled = -1; fpx = min(pend_s, bo[k]) - slip
            if filled != 0 and pend_sl > 0:
                pos = filled; e_px = fpx; R = pend_sl; k_in = k
                sl = e_px - R if pos == 1 else e_px + R
                tp = 0.0
                if pend_tp > 0:
                    tp = e_px + pend_tp if pos == 1 else e_px - pend_tp
                best = 0.0; worst = 0.0; part_done = False; moved = False
                pend_b = np.nan; pend_s = np.nan
                day_count += 1
                if not entry_same_bar_check:
                    # judge only the close of the fill bar (path inside the bar unknown)
                    if pos == 1:
                        best = max(0.0, bc[k] - e_px); worst = min(0.0, bc[k] - e_px)
                    else:
                        best = max(0.0, e_px - ac[k]); worst = min(0.0, e_px - ac[k])
                    continue

        # --- manage open position ---
        if pos != 0:
            exit_px = 0.0; reason = 0
            if pos == 1:
                if bl[k] <= sl:
                    exit_px = min(sl, bo[k]) - slip; reason = X_MOVED_SL if moved else X_SL
                elif tp > 0 and bh[k] >= tp:
                    exit_px = tp; reason = X_TP
            else:
                if ah[k] >= sl:
                    exit_px = max(sl, ao[k]) + slip; reason = X_MOVED_SL if moved else X_SL
                elif tp > 0 and al[k] <= tp:
                    exit_px = tp; reason = X_TP
            if reason == 0 and max_hold > 0 and ex_sec[k] - ex_sec[k_in] >= max_hold:
                exit_px = bc[k] if pos == 1 else ac[k]; reason = X_TIME
            if reason != 0:
                pnl = (exit_px - e_px) * pos
                if part_done:
                    pnl = part_frac * (part_px - e_px) * pos + (1 - part_frac) * pnl
                pnl -= 2 * comm
                t_in[nt] = k_in; t_out[nt] = k; t_dir[nt] = pos; t_px_in[nt] = e_px; t_px_out[nt] = exit_px
                t_pnl[nt] = pnl; t_r[nt] = pnl / R; t_reason[nt] = reason
                if pos == 1:
                    worst = min(worst, bl[k] - e_px)
                else:
                    worst = min(worst, e_px - ah[k])
                t_mfe[nt] = best / R; t_mae[nt] = worst / R
                nt += 1; pos = 0
                continue
            # excursions, partial, BE and trailing take effect from the next bar
            if pos == 1:
                fav = bh[k] - e_px; adv = bl[k] - e_px
            else:
                fav = e_px - al[k]; adv = e_px - ah[k]
            if fav > best:
                best = fav
            if adv < worst:
                worst = adv
            if part_r > 0 and not part_done and best >= part_r * R:
                part_done = True; part_px = e_px + pos * part_r * R
            if be_trig > 0 and best >= be_trig * R:
                nsl = e_px + pos * be_off * R
                if (pos == 1 and nsl > sl) or (pos == -1 and nsl < sl):
                    sl = nsl; moved = True
            if tr_trig > 0 and best >= tr_trig * R:
                nsl = e_px + pos * (best - tr_dist * R)
                if (pos == 1 and nsl > sl) or (pos == -1 and nsl < sl):
                    sl = nsl; moved = True

    return (t_in[:nt], t_out[:nt], t_dir[:nt], t_px_in[:nt], t_px_out[:nt], t_pnl[:nt],
            t_r[:nt], t_reason[:nt], t_mfe[:nt], t_mae[:nt])


def run(mkt: Market, it: Intents, be_trig=0.0, be_off=0.0, tr_trig=0.0, tr_dist=0.0,
        part_r=0.0, part_frac=0.0, max_hold_min=0, comm=0.0, slip=0.0, max_per_day=99,
        entry_same_bar_check=False) -> pd.DataFrame:
    """comm is per side in price units (e.g. EURUSD $3.5/lot/side = 0.000035)."""
    bo, bh, bl, bc, ao, ah, al, ac = mkt.ex_arrays
    max_hold = int(max_hold_min * 60) if max_hold_min else 0
    day = mkt.sig.day.values.astype(np.int64)
    res = _engine(bo, bh, bl, bc, ao, ah, al, ac, mkt.ex_sec, mkt.x2s, mkt.first, day,
                  it.ent, it.lvl_buy, it.lvl_sell, it.sl, it.tp, it.ex,
                  be_trig, be_off, tr_trig, tr_dist, part_r, part_frac,
                  max_hold, comm, slip, max_per_day, entry_same_bar_check)
    cols = ["k_in", "k_out", "dir", "px_in", "px_out", "pnl", "R", "reason", "mfe", "mae"]
    tr = pd.DataFrame(dict(zip(cols, res)))
    tr["t_in"] = mkt.ex.time.values[tr.k_in.values]
    tr["t_out"] = mkt.ex.time.values[tr.k_out.values]
    tr["sym"] = mkt.sym
    return tr


def stats(tr: pd.DataFrame, years: float | None = None) -> dict:
    if len(tr) == 0:
        return {"n": 0}
    r = tr.R.values
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    if years is None:
        years = max((tr.t_out.max() - tr.t_in.min()).days / 365.25, 1e-9)
    daily = tr.groupby(tr.t_out.dt.floor("D")).R.sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if len(daily) > 2 and daily.std() > 0 else np.nan
    return {
        "n": len(r), "per_yr": round(len(r) / years, 1), "win%": round(100 * len(wins) / len(r), 1),
        "avgR": round(r.mean(), 3), "PF": round(pf, 2), "totR": round(r.sum(), 1),
        "maxDD_R": round(dd, 1), "sharpe_d": round(sharpe, 2),
    }


def yearly(tr: pd.DataFrame) -> pd.DataFrame:
    g = tr.groupby(tr.t_in.dt.year)
    return pd.DataFrame({
        "n": g.R.size(), "win%": (g.R.apply(lambda s: (s > 0).mean() * 100)).round(1),
        "avgR": g.R.mean().round(3), "totR": g.R.sum().round(1),
        "PF": g.R.apply(lambda s: s[s > 0].sum() / max(-s[s <= 0].sum(), 1e-9)).round(2),
    })
