"""Signal generators. Each returns bt.Intents on the market's signal grid.

All price levels are expressed the way an MT5 EA sees them: chart prices are Bid,
a buy-stop is placed at (bid level + current spread) so it triggers when Bid
reaches the level, a sell-stop at the bid level.
"""
import numpy as np
import pandas as pd

from bt import Intents, Market


def _group_first_last(key: np.ndarray):
    """Start index of the run each element belongs to (key must be sorted by run)."""
    starts = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1]
    run_id = np.cumsum(np.r_[0, (key[1:] != key[:-1]).astype(np.int64)])
    return starts, run_id


def atr_daily(sig: pd.DataFrame, n: int = 14) -> np.ndarray:
    """ATR of completed trading days (fx day), mapped onto each signal bar (no look-ahead)."""
    d = sig.groupby("day").agg(h=("bh", "max"), l=("bl", "min"), c=("bc", "last"))
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    atr = tr.rolling(n, min_periods=n).mean().shift(1)
    return sig.day.map(atr).values


def orb(mkt: Market, tz_col="ny_min", open_min=570, or_len=15, entry_until=120, flat_min=955,
        buffer_frac=0.0, sl_frac=1.0, sl_atr=0.0, tp_r=0.0, direction="both", min_or_atr=0.0,
        max_or_atr=9.0, first_bar_dir=False, dow_mask=(0, 1, 2, 3, 4)) -> Intents:
    """Opening-range breakout.

    Range = bars in [open_min, open_min+or_len) of the local clock `tz_col`.
    Stop orders at range high/low (+/- buffer*range) until open_min+or_len+entry_until.
    SL = sl_frac*range (or sl_atr*daily ATR if >0), TP = tp_r*SL (0 = hold to flat_min).
    first_bar_dir: only trade in the direction of the opening-range candle.
    """
    s = mkt.sig
    it = Intents(len(s))
    clk = s[tz_col].values
    date = s.ny_date.values if tz_col == "ny_min" else s.day.values
    in_or = (clk >= open_min) & (clk < open_min + or_len)
    h = np.where(in_or, s.bh.values, -np.inf)
    l = np.where(in_or, s.bl.values, np.inf)
    o = np.where(in_or, s.bo.values, np.nan)
    c = np.where(in_or, s.bc.values, np.nan)
    df = pd.DataFrame({"d": date, "h": h, "l": l, "o": o, "c": c})
    g = df.groupby("d")
    or_h = g.h.transform("max").values
    or_l = g.l.transform("min").values
    or_o = g.o.transform("first").values
    or_c = g.c.transform("last").values
    rng = or_h - or_l
    atr = atr_daily(s)
    window = (clk >= open_min + or_len) & (clk < open_min + or_len + entry_until)
    valid = window & np.isfinite(rng) & (rng > 0) & np.isfinite(atr)
    valid &= (rng >= min_or_atr * atr) & (rng <= max_or_atr * atr)
    valid &= np.isin(s.dow.values, dow_mask)
    spr = (s.ac - s.bc).values
    buf = buffer_frac * np.where(np.isfinite(rng), rng, 0.0)
    lvl_b = or_h + buf + spr
    lvl_s = or_l - buf
    sl = sl_atr * atr if sl_atr > 0 else sl_frac * rng
    # price must still be inside the range for the stop order to make sense
    inside = (s.bc.values < or_h + buf) & (s.bc.values > or_l - buf)
    want_long = direction in ("both", "long")
    want_short = direction in ("both", "short")
    if first_bar_dir:
        up = or_c > or_o
        long_ok = valid & inside & up & want_long
        short_ok = valid & inside & ~up & want_short
    else:
        long_ok = valid & inside & want_long
        short_ok = valid & inside & want_short
    both = long_ok & short_ok
    it.ent[both] = 3
    it.ent[long_ok & ~short_ok] = 2
    it.ent[short_ok & ~long_ok] = -2
    it.lvl_buy[:] = lvl_b
    it.lvl_sell[:] = lvl_s
    it.sl[:] = sl
    it.tp[:] = tp_r * sl if tp_r > 0 else 0.0
    it.ex[(clk >= flat_min) | (clk < open_min)] = 2
    return it


def session_mask(s: pd.DataFrame, clock: str, start: int, end: int) -> np.ndarray:
    c = s[clock].values
    return (c >= start) & (c < end) if start <= end else (c >= start) | (c < end)


def atr_bars(s: pd.DataFrame, n: int) -> np.ndarray:
    h, l, c = s.bh.values, s.bl.values, s.bc.values
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=n).mean().values


def mean_reversion(mkt: Market, n=20, k_entry=2.0, sl_atr=1.5, tp_mode="mean", tp_r=1.0,
                   min_tp_spread=2.0, confirm=False, clock="utc_min", start=0, end=1440,
                   exit_at_mean=True, max_spread_atr=0.5, trend_n=0, trend_max=9.0) -> Intents:
    """Fade stretches beyond k_entry standard deviations from an n-bar mean (bid prices).

    tp_mode: "mean" -> TP distance = distance to mean at signal; "r" -> tp_r * SL.
    confirm: enter only once the bar closes back inside the band.
    trend_n>0: skip when |close - SMA(trend_n)| > trend_max * ATR (strong trend).
    """
    s = mkt.sig
    it = Intents(len(s))
    c = s.bc.values
    ma = pd.Series(c).rolling(n, min_periods=n).mean().values
    sd = pd.Series(c).rolling(n, min_periods=n).std().values
    atr = atr_bars(s, n)
    z = (c - ma) / sd
    zp = np.r_[np.nan, z[:-1]]
    spr = (s.ac - s.bc).values
    ok = session_mask(s, clock, start, end) & np.isfinite(z) & (spr <= max_spread_atr * atr)
    if trend_n:
        tma = pd.Series(c).rolling(trend_n, min_periods=trend_n).mean().values
        ok &= np.abs(c - tma) <= trend_max * atr
    if confirm:
        long_sig = ok & (zp < -k_entry) & (z >= -k_entry)
        short_sig = ok & (zp > k_entry) & (z <= k_entry)
    else:
        long_sig = ok & (z < -k_entry)
        short_sig = ok & (z > k_entry)
    dist = np.abs(ma - c)
    tp = dist if tp_mode == "mean" else tp_r * sl_atr * atr
    good_tp = tp >= min_tp_spread * spr
    long_sig &= good_tp
    short_sig &= good_tp
    it.ent[long_sig] = 1
    it.ent[short_sig] = -1
    it.sl[:] = sl_atr * atr
    it.tp[:] = np.where(np.isfinite(tp), tp, 0.0)
    if exit_at_mean:
        it.ex[c >= ma] = 1
        it.ex[c <= ma] = -1
    return it


def breakout(mkt: Market, n=20, sl_atr=1.5, tp_r=0.0, atr_n=20, clock="utc_min", start=0, end=1440,
             trend_n=0, max_spread_atr=0.3, min_width_atr=0.0, max_width_atr=99.0) -> Intents:
    """Donchian breakout with stop orders at the n-bar high/low (optionally trend filtered)."""
    s = mkt.sig
    it = Intents(len(s))
    hh = pd.Series(s.bh.values).rolling(n, min_periods=n).max().values
    ll = pd.Series(s.bl.values).rolling(n, min_periods=n).min().values
    atr = atr_bars(s, atr_n)
    spr = (s.ac - s.bc).values
    width = hh - ll
    ok = session_mask(s, clock, start, end) & np.isfinite(hh) & np.isfinite(atr) & (spr <= max_spread_atr * atr)
    ok &= (width >= min_width_atr * atr) & (width <= max_width_atr * atr)
    c = s.bc.values
    want_l = ok.copy(); want_s = ok.copy()
    if trend_n:
        tma = pd.Series(c).rolling(trend_n, min_periods=trend_n).mean().values
        want_l &= c > tma
        want_s &= c < tma
    it.ent[want_l & want_s] = 3
    it.ent[want_l & ~want_s] = 2
    it.ent[want_s & ~want_l] = -2
    it.lvl_buy[:] = hh + spr
    it.lvl_sell[:] = ll
    it.sl[:] = sl_atr * atr
    it.tp[:] = tp_r * sl_atr * atr if tp_r > 0 else 0.0
    return it


def noise_prep(mkt: Market, lookback=14, clock="ny_min", open_min=570, close_min=960) -> dict:
    """Per-bar session open, previous close, noise width sigma and session VWAP (cached on the market)."""
    cache = mkt.__dict__.setdefault("_noise_cache", {})
    key = (lookback, clock, open_min, close_min)
    if key in cache:
        return cache[key]
    s = mkt.sig
    clk = s[clock].values
    date = s.ny_date.values if clock == "ny_min" else s.day.values
    rth = (clk >= open_min) & (clk < close_min)
    df = pd.DataFrame({"date": date, "clk": clk, "c": s.bc.values, "rth": rth})
    r = df[df.rth]
    day_open = r.groupby("date").c.first()          # close of the first session bar
    day_close = r.groupby("date").c.last()
    prev_close = day_close.shift(1)
    o = df.date.map(day_open).values
    pc = df.date.map(prev_close).values
    # per-day minute grid, forward-filled inside the session (same as the EA)
    piv = r.pivot_table(index="date", columns="clk", values="c", aggfunc="last")
    piv = piv.reindex(columns=range(open_min, close_min)).ffill(axis=1)
    piv = piv.T.fillna(day_open.reindex(piv.index)).T
    move = (piv.div(day_open.reindex(piv.index), axis=0) - 1).abs()
    sig_tab = move.rolling(lookback, min_periods=lookback).mean().shift(1)
    di = pd.Index(sig_tab.index).get_indexer(date)
    ci = np.clip(clk - open_min, 0, close_min - open_min - 1)
    vals = sig_tab.values
    sigma = np.where((di >= 0) & rth, vals[np.maximum(di, 0), ci], np.nan)
    tp_px = (s.bh.values + s.bl.values + s.bc.values) / 3
    w = np.where(rth, s.n.values.astype(float), 0.0)
    cum_pv = pd.Series(tp_px * w).groupby(date).cumsum().values
    cum_v = pd.Series(w).groupby(date).cumsum().values
    vwap = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), np.nan)
    out = dict(clk=clk, rth=rth, o=o, pc=pc, sigma=sigma, vwap=vwap, c=s.bc.values)
    cache[key] = out
    return out


def noise_area(mkt: Market, lookback=14, check_every=30, first_check=600, last_entry=930, flat_min=955,
               vol_mult=1.0, sl_mode="band", sl_sigma=1.0, use_vwap=True, tp_r=0.0,
               clock="ny_min", open_min=570, close_min=960, min_sl_sigma=0.25, long_only=False,
               exit_mode="band") -> Intents:
    """Intraday momentum on an index (Zarattini, Aziz & Barbon 2024, 'Beat the Market').

    Noise band around the session open: sigma(t) = mean over `lookback` prior days of
    |close(t)/open - 1| at the same minute. Long above max(open, prev close)*(1+m*sigma),
    short below min(open, prev close)*(1-m*sigma), checked every `check_every` minutes.
    Exit when price closes back behind max(band, VWAP) (long) / min(band, VWAP) (short).
    """
    p = noise_prep(mkt, lookback, clock, open_min, close_min)
    it = Intents(len(mkt.sig))
    clk, rth, o, pc, c = p["clk"], p["rth"], p["o"], p["pc"], p["c"]
    sigma = p["sigma"] * vol_mult
    ub = np.fmax(o, pc) * (1 + sigma)
    lb = np.fmin(o, pc) * (1 - sigma)
    vwap = p["vwap"]
    check = rth & (((clk + 1) % check_every) == 0) & (clk + 1 >= first_check)
    entry_ok = check & (clk + 1 <= last_entry) & np.isfinite(ub) & np.isfinite(lb)
    long_stop = np.fmax(ub, vwap) if use_vwap else ub
    short_stop = np.fmin(lb, vwap) if use_vwap else lb
    go_l = entry_ok & (c > ub)
    go_s = entry_ok & (c < lb) & (not long_only)
    it.ent[go_l] = 1
    it.ent[go_s] = -1
    sig_px = p["sigma"] * o
    if sl_mode == "band":
        sl = np.where(go_l, c - long_stop, np.where(go_s, short_stop - c, np.nan))
        sl = np.maximum(sl, min_sl_sigma * sig_px)
    else:
        sl = sl_sigma * sig_px
    it.sl[:] = sl
    it.tp[:] = tp_r * sl if tp_r > 0 else 0.0
    # exit_mode: "band" = close when back behind max(band,VWAP)/min(band,VWAP) (paper rule),
    # "opposite" = close only when the opposite band is crossed, "none" = SL/TP/BE/session end only
    if exit_mode == "band":
        x_long = check & (c < long_stop)
        x_short = check & (c > short_stop)
    elif exit_mode == "opposite":
        x_long = check & (c < lb)
        x_short = check & (c > ub)
    else:
        x_long = np.zeros(len(c), bool)
        x_short = np.zeros(len(c), bool)
    it.ex[x_long] = 1
    it.ex[x_short] = -1
    it.ex[x_long & x_short] = 2
    it.ex[(clk >= flat_min) | (clk < open_min)] = 2
    return it


def half_hour_momentum(mkt: Market, sl_frac=1.0, entry_min=930, flat_min=959, min_move=0.0) -> Intents:
    """Trade the last half hour in the direction of the first half hour (Gao, Han, Li & Zhou 2018)."""
    s = mkt.sig
    it = Intents(len(s))
    clk = s.ny_min.values
    date = s.ny_date.values
    c = s.bc.values
    df = pd.DataFrame({"date": date, "clk": clk, "c": c})
    o = df[df.clk == 570].groupby("date").c.first()
    x = df[df.clk == 599].groupby("date").c.first()
    first_ret = (x / o - 1)
    rng_first = df[(df.clk >= 570) & (df.clk < 600)].groupby("date").c.agg(lambda v: v.max() - v.min())
    fr = df.date.map(first_ret).values
    rf = df.date.map(rng_first).values
    sig_bar = clk == entry_min - 1
    ok = sig_bar & np.isfinite(fr) & (np.abs(fr) >= min_move)
    it.ent[ok & (fr > 0)] = 1
    it.ent[ok & (fr < 0)] = -1
    it.sl[:] = sl_frac * rf
    it.ex[(clk >= flat_min) | (clk < 570)] = 2
    return it


def failed_breakout(mkt: Market, lookback=30, vol_mult=1.5, check_every=30, first_check=630, last_entry=900,
                    flat_min=955, back_to="open", sl_sigma=1.0, tp_r=2.0) -> Intents:
    """Fade a noise-band breakout that has failed.

    Earlier today price closed outside the band at a check; now (at a later check) it has come all the
    way back to the reference level (session open / band edge). Trade toward the opposite side.
    """
    p = noise_prep(mkt, lookback)
    s = mkt.sig
    it = Intents(len(s))
    clk, rth, o, pc, c = p["clk"], p["rth"], p["o"], p["pc"], p["c"]
    sig = p["sigma"] * vol_mult
    ub = np.fmax(o, pc) * (1 + sig)
    lb = np.fmin(o, pc) * (1 - sig)
    check = rth & (((clk + 1) % check_every) == 0) & (clk + 1 >= 600)
    date = s.ny_date.values
    up_brk = pd.Series(np.where(check, c > ub, False)).groupby(date).cummax().values
    dn_brk = pd.Series(np.where(check, c < lb, False)).groupby(date).cummax().values
    ok = check & (clk + 1 >= first_check) & (clk + 1 <= last_entry) & np.isfinite(sig)
    ref_hi = np.fmax(o, pc) if back_to == "band" else o
    ref_lo = np.fmin(o, pc) if back_to == "band" else o
    go_s = ok & up_brk & ~dn_brk & (c < ref_hi)
    go_l = ok & dn_brk & ~up_brk & (c > ref_lo)
    it.ent[go_s] = -1
    it.ent[go_l] = 1
    sl = sl_sigma * p["sigma"] * o
    it.sl[:] = sl
    it.tp[:] = tp_r * sl
    it.ex[(clk >= flat_min) | (clk < 570)] = 2
    return it


def gap_fade(mkt: Market, min_gap=0.001, max_gap=0.006, sl_mult=1.0, exit_min=660, entry_min=575) -> Intents:
    """Fade the overnight gap at the cash open toward the previous close (target = previous close)."""
    p = noise_prep(mkt, 30)
    s = mkt.sig
    it = Intents(len(s))
    clk, o, pc, c = p["clk"], p["o"], p["pc"], p["c"]
    gap = o / pc - 1
    sig_bar = clk == entry_min - 1
    ok = sig_bar & np.isfinite(gap) & (np.abs(gap) >= min_gap) & (np.abs(gap) <= max_gap)
    dist = np.abs(c - pc)
    it.ent[ok & (gap > 0) & (c > pc)] = -1
    it.ent[ok & (gap < 0) & (c < pc)] = 1
    it.sl[:] = np.maximum(sl_mult * np.abs(o - pc), 1e-9)
    it.tp[:] = dist
    it.ex[(clk >= exit_min) | (clk < 570)] = 2
    return it


def swing_breakout(mkt: Market, n=100, atr_n=24, sl_atr=2.5, trend_n=0, entry_utc=(420, 1200),
                   flat_friday_utc=1230, long_only=False, tp_r=0.0) -> Intents:
    """Multi-day trend following on the signal grid (e.g. H1): stop orders at the n-bar high/low.

    Entries only inside the liquid UTC window; everything is closed on Friday at flat_friday_utc
    (no weekend risk). Stops: sl_atr x ATR(atr_n); trailing/TP handled by the engine.
    """
    s = mkt.sig
    it = Intents(len(s))
    hh = pd.Series(s.bh.values).rolling(n, min_periods=n).max().values
    ll = pd.Series(s.bl.values).rolling(n, min_periods=n).min().values
    atr = atr_bars(s, atr_n)
    spr = (s.ac - s.bc).values
    c = s.bc.values
    utc = s.utc_min.values
    dow = pd.DatetimeIndex(s.time).dayofweek.values
    ok = (utc >= entry_utc[0]) & (utc < entry_utc[1]) & np.isfinite(hh) & np.isfinite(atr) & ((dow < 4) | ((dow == 4) & (utc < flat_friday_utc - 240)))
    want_l = ok.copy(); want_s = ok.copy() & (not long_only)
    if trend_n:
        tma = pd.Series(c).rolling(trend_n, min_periods=trend_n).mean().values
        want_l &= c > tma
        want_s &= c < tma
    it.ent[want_l & want_s] = 3
    it.ent[want_l & ~want_s] = 2
    it.ent[want_s & ~want_l] = -2
    it.lvl_buy[:] = hh + spr
    it.lvl_sell[:] = ll
    it.sl[:] = sl_atr * atr
    it.tp[:] = tp_r * sl_atr * atr if tp_r > 0 else 0.0
    it.ex[(dow == 4) & (utc >= flat_friday_utc)] = 2
    it.ex[dow >= 5] = 2
    return it
