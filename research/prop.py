"""Prop-firm challenge simulation on top of trade lists (R multiples).

Rules modelled (defaults = common 2-step challenge, phase 1):
  profit target 10 %, max daily loss 5 % of initial balance (incl. floating),
  max total loss 10 % of initial balance, minimum 4 trading days.
The EA-side protections are modelled too: risk % per trade of current balance,
a self-imposed daily stop (no new trades once the day's loss reaches it) and
stopping once the target is reached.
"""
import numba as nb
import numpy as np
import pandas as pd


def prep(trades: pd.DataFrame) -> pd.DataFrame:
    tr = trades.sort_values("t_out").reset_index(drop=True).copy()
    # prop "day" = New York 17:00 roll (≈ midnight CE(S)T used by most firms)
    ny_in = pd.DatetimeIndex(tr.t_in).tz_localize("UTC").tz_convert("America/New_York")
    ny_out = pd.DatetimeIndex(tr.t_out).tz_localize("UTC").tz_convert("America/New_York")
    tr["d_in"] = (ny_in + pd.Timedelta(hours=7)).normalize().tz_localize(None).values.astype("datetime64[D]").astype(np.int64)
    tr["d_out"] = (ny_out + pd.Timedelta(hours=7)).normalize().tz_localize(None).values.astype("datetime64[D]").astype(np.int64)
    return tr


@nb.njit(cache=True)
def _challenge(d_in, d_out, R, mae, start_idx, risk, target, daily_lim, max_loss,
               min_days, max_days, daily_stop):
    n_starts = len(start_idx)
    outcome = np.zeros(n_starts, np.int8)   # 1 pass, -1 fail, 0 timeout / out of data
    days_used = np.zeros(n_starts, np.int64)
    worst_dd = np.zeros(n_starts)
    n = len(R)
    for s in range(n_starts):
        i0 = start_idx[s]
        if i0 >= n:
            continue
        bal = 1.0
        day0 = d_in[i0]
        cur_day = -1
        day_start = 1.0
        day_real = 0.0
        traded_days = 0
        last_traded_day = -1
        low = 1.0
        for i in range(i0, n):
            if d_in[i] - day0 >= max_days:
                break
            if d_out[i] != cur_day:
                cur_day = d_out[i]; day_start = bal; day_real = 0.0
            # EA daily stop: skip new trades once today's realised loss hits the stop
            if daily_stop > 0 and d_in[i] == cur_day and day_real <= -daily_stop:
                continue
            r_usd = risk * bal
            floating_low = bal + mae[i] * r_usd
            if floating_low < low:
                low = floating_low
            # daily loss uses initial balance (1.0) as reference, incl. floating
            if day_start - floating_low >= daily_lim or 1.0 - floating_low >= max_loss:
                outcome[s] = -1; days_used[s] = d_out[i] - day0 + 1
                break
            pnl = R[i] * r_usd
            bal += pnl
            day_real += pnl
            if d_in[i] != last_traded_day:
                traded_days += 1; last_traded_day = d_in[i]
            if bal < low:
                low = bal
            if day_start - bal >= daily_lim or 1.0 - bal >= max_loss:
                outcome[s] = -1; days_used[s] = d_out[i] - day0 + 1
                break
            if bal - 1.0 >= target and traded_days >= min_days:
                outcome[s] = 1; days_used[s] = d_out[i] - day0 + 1
                break
        worst_dd[s] = 1.0 - low
    return outcome, days_used, worst_dd


def challenge(trades: pd.DataFrame, risk=0.005, target=0.10, daily_lim=0.05, max_loss=0.10,
              min_days=4, max_days=365, daily_stop=0.0, start_every_days=1) -> dict:
    tr = prep(trades)
    if len(tr) == 0:
        return {}
    first_day = tr.d_in.min(); last_day = tr.d_out.max()
    # start points: first trade index on/after each calendar day
    starts = np.arange(first_day, last_day - 30, start_every_days)
    order_in = np.searchsorted(tr.d_out.values, starts, side="left")
    oc, days, wdd = _challenge(tr.d_in.values, tr.d_out.values, tr.R.values.astype(np.float64),
                               tr.mae.values.astype(np.float64), order_in.astype(np.int64),
                               risk, target, daily_lim, max_loss, min_days, max_days, daily_stop)
    passed = oc == 1
    return {
        "starts": len(oc), "pass%": round(100 * passed.mean(), 1), "fail%": round(100 * (oc == -1).mean(), 1),
        "open%": round(100 * (oc == 0).mean(), 1),
        "med_days": float(np.median(days[passed])) if passed.any() else np.nan,
        "p75_days": float(np.percentile(days[passed], 75)) if passed.any() else np.nan,
    }


def equity_curve(trades: pd.DataFrame, risk=0.005, daily_stop=0.0) -> pd.DataFrame:
    """Compounded balance path (balance 1.0 at start) with the EA daily stop applied."""
    tr = prep(trades)
    bal = 1.0; cur_day = None; day_real = 0.0; rows = []
    for d_in, d_out, r, mae, t in zip(tr.d_in, tr.d_out, tr.R, tr.mae, tr.t_out):
        if d_out != cur_day:
            cur_day = d_out; day_real = 0.0
        if daily_stop > 0 and d_in == cur_day and day_real <= -daily_stop:
            continue
        pnl = r * risk * bal
        low = bal + mae * risk * bal
        bal += pnl; day_real += pnl
        rows.append((t, bal, low))
    return pd.DataFrame(rows, columns=["t", "bal", "low"])


def curve_stats(ec: pd.DataFrame) -> dict:
    if len(ec) == 0:
        return {}
    peak = np.maximum.accumulate(np.r_[1.0, ec.bal.values])[1:]
    dd = (peak - np.minimum(ec.bal.values, ec.low.values)) / peak
    daily = ec.set_index("t").bal.resample("D").last().dropna()
    dret = daily.pct_change().dropna()
    monthly = ec.set_index("t").bal.resample("ME").last().dropna()
    mret = monthly.pct_change().fillna(monthly.iloc[0] - 1.0)
    days_neg = (ec.set_index("t").bal.resample("D").last().dropna().diff() < 0).mean()
    years = max((ec.t.iloc[-1] - ec.t.iloc[0]).days / 365.25, 1e-9)
    return {
        "final": round(ec.bal.iloc[-1], 3), "CAGR%": round(100 * (ec.bal.iloc[-1] ** (1 / years) - 1), 1),
        "maxDD%": round(100 * dd.max(), 2), "worst_day%": round(100 * dret.min(), 2) if len(dret) else np.nan,
        "sharpe": round(dret.mean() / dret.std() * np.sqrt(252), 2) if len(dret) > 2 else np.nan,
        "pos_months%": round(100 * (mret > 0).mean(), 1), "worst_month%": round(100 * mret.min(), 2),
        "neg_days%": round(100 * days_neg, 1),
    }
