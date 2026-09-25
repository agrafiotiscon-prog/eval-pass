"""Sprint-mode challenge simulation: pass fast, never breach the firm's limits by design.

Event-driven (entries and exits in time order, trades on several symbols can overlap).
Every entry is sized in % of the INITIAL balance and capped by a risk budget:
    risk <= daily_guard - (today's loss so far) - (risk already open)
    risk <= loss_guard  - (total loss so far)   - (risk already open)
so a stop-loss can never take the account through the guard levels (only a gap
through the stop can). Sizing policies:
    "fixed":  risk = r_max
    "target": risk = clip((target - profit) / k, r_min, r_max)
              (k = 2.5 -> one take-profit at 2.5R would finish the challenge)
"""
import numba as nb
import numpy as np
import pandas as pd

from prop import prep


def build_events(trades: pd.DataFrame):
    tr = prep(trades).sort_values("t_in").reset_index(drop=True)
    n = len(tr)
    t = np.r_[tr.t_in.values.astype("datetime64[s]").astype(np.int64), tr.t_out.values.astype("datetime64[s]").astype(np.int64)]
    kind = np.r_[np.ones(n, np.int8), np.zeros(n, np.int8)]          # 1 entry, 0 exit
    idx = np.r_[np.arange(n), np.arange(n)]
    day = np.r_[tr.d_in.values, tr.d_out.values]
    order = np.lexsort((kind, t))                                     # exits before entries at equal time
    R = tr.R.values.astype(np.float64)
    # floating low cannot be worse than the realised loss once the stop filled (bar lows after the fill are noise)
    mae = np.maximum(tr.mae.values, np.minimum(R, -1.0)).astype(np.float64)
    return dict(kind=kind[order], idx=idx[order], day=day[order].astype(np.int64), R=R, mae=mae, n=n)


@nb.njit(cache=True)
def _attempt(kind, idx, day, R, mae, n, e0, policy, r_max, r_min, k, target, daily_lim, max_loss,
             daily_guard, loss_guard, min_days, max_days, halt_dd):
    """Run one challenge attempt from event e0. Returns (outcome, last_event, days_elapsed)."""
    risk = np.zeros(n)
    bal = 1.0
    cur_day = -1
    day_start = 1.0
    open_sum = 0.0
    traded = 0
    last_trade_day = -1
    d0 = day[e0]
    low_bal = 1.0
    for e in range(e0, len(kind)):
        d = day[e]
        if d - d0 >= max_days:
            return 0, e, d - d0, low_bal
        if d != cur_day:
            cur_day = d
            day_start = bal
        i = idx[e]
        if kind[e] == 1:
            profit = bal - 1.0
            if policy == 1:
                r = (target - profit) / k
                r = min(max(r, r_min), r_max)
            else:
                r = r_max
            daily_room = daily_guard - (day_start - bal) - open_sum
            total_room = loss_guard - (1.0 - bal) - open_sum
            r = min(r, daily_room, total_room)
            if r < r_min:
                continue
            risk[i] = r
            open_sum += r
            if d != last_trade_day:
                traded += 1
                last_trade_day = d
        else:
            r = risk[i]
            if r == 0.0:
                continue
            low = bal + mae[i] * r
            if low < low_bal:
                low_bal = low
            if day_start - low >= daily_lim or 1.0 - low >= max_loss:
                return -1, e, d - d0 + 1, low_bal
            bal += R[i] * r
            open_sum -= r
            risk[i] = 0.0
            if day_start - bal >= daily_lim or 1.0 - bal >= max_loss:
                return -1, e, d - d0 + 1, low_bal
            if bal - 1.0 >= target and traded >= min_days:
                return 1, e, d - d0 + 1, low_bal
            # EA max-loss halt: attempt abandoned (restart a new challenge)
            if halt_dd > 0 and 1.0 - bal >= halt_dd and open_sum <= 1e-12:
                return -2, e, d - d0 + 1, low_bal
    return 0, len(kind) - 1, day[len(kind) - 1] - d0, low_bal


@nb.njit(cache=True)
def _run_all(kind, idx, day, R, mae, n, starts, policy, r_max, r_min, k, target, daily_lim, max_loss,
             daily_guard, loss_guard, min_days, window, retry_cap_days, halt_dd):
    ns = len(starts)
    single = np.zeros(ns, np.int8)
    single_days = np.zeros(ns, np.int64)
    to_funded = np.full(ns, -1, np.int64)      # calendar days until first pass with free restarts
    attempts = np.zeros(ns, np.int64)
    lows = np.ones(ns)
    for s in range(ns):
        e0 = starts[s]
        if e0 >= len(kind):
            continue
        oc, e_end, dd, lb = _attempt(kind, idx, day, R, mae, n, e0, policy, r_max, r_min, k, target,
                                     daily_lim, max_loss, daily_guard, loss_guard, min_days, window, halt_dd)
        single[s] = oc
        single_days[s] = dd
        lows[s] = lb
        # free retries: no time limit per attempt, restart the day after a failure
        d_start = day[e0]
        e = e0
        a = 0
        while e < len(kind) and day[e] - d_start < retry_cap_days:
            a += 1
            oc2, e_end2, dd2, lb2 = _attempt(kind, idx, day, R, mae, n, e, policy, r_max, r_min, k, target,
                                        daily_lim, max_loss, daily_guard, loss_guard, min_days, 100000, halt_dd)
            if oc2 == 1:
                to_funded[s] = day[e_end2] - d_start + 1
                break
            if oc2 == 0:
                break
            nd = day[e_end2] + 1
            while e < len(kind) and (day[e] < nd or kind[e] == 0):
                e += 1
        attempts[s] = a
    return single, single_days, to_funded, attempts, lows


def simulate(trades: pd.DataFrame, policy="target", r_max=0.04, r_min=0.0025, k=2.5, target=0.10,
             daily_lim=0.05, max_loss=0.10, daily_guard=0.045, loss_guard=0.095, min_days=0,
             window=7, retry_cap_days=730, halt_dd=0.0) -> dict:
    ev = build_events(trades)
    kind, idx, day = ev["kind"], ev["idx"], ev["day"]
    first, last = day.min(), day.max()
    start_days = np.arange(first, last - max(window, 30))
    # first ENTRY event on/after each start day
    entry_pos = np.flatnonzero(kind == 1)
    starts = entry_pos[np.minimum(np.searchsorted(day[entry_pos], start_days), len(entry_pos) - 1)]
    single, sdays, funded, att, lows = _run_all(kind, idx, day, ev["R"], ev["mae"], ev["n"], starts.astype(np.int64),
                                          1 if policy == "target" else 0, r_max, r_min, k, target, daily_lim,
                                          max_loss, daily_guard, loss_guard, min_days, window, retry_cap_days, halt_dd)
    ok = funded > 0
    return {
        "pass%": round(100 * (single == 1).mean(), 1), "fail%": round(100 * (single == -1).mean(), 1),
        "halt%": round(100 * (single == -2).mean(), 1),
        "open%": round(100 * (single == 0).mean(), 1),
        "med_days_if_pass": float(np.median(sdays[single == 1])) if (single == 1).any() else np.nan,
        "retry_funded_%": round(100 * ok.mean(), 1),
        "retry_med_days": float(np.median(funded[ok])) if ok.any() else np.nan,
        "retry_p75_days": float(np.percentile(funded[ok], 75)) if ok.any() else np.nan,
        "retry_mean_attempts": round(float(att[ok].mean()), 2) if ok.any() else np.nan,
        "deepDD8%_in_window": round(100 * (lows <= 0.92).mean(), 1),
        "deepDD5%_in_window": round(100 * (lows <= 0.95).mean(), 1),
    }
