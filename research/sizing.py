"""Account-level position-sizing policies for a prop challenge (event-driven, same rules as sprint.py).

risk per trade (fraction of the INITIAL balance) = policy(state), then capped by the daily and total
worst-case budgets (open stops included). Policies:
  0 fixed      r = a
  1 cushion    r = clip(b * (equity - floor), rmin, a)          floor = 1 - halt        (CPPI-style)
  2 step-up    r = a while profit < c, else b                                          (house money)
  3 dd-cut     r = a, but a * b while drawdown from peak >= c
  4 target     r = clip((target - profit) / b, rmin, a)                               (sprint)
  5 cushion+   r = clip(b * (equity - floor), rmin, a), and a * 0.5 once profit >= c (protect near target)
"""
import numba as nb
import numpy as np
import pandas as pd

from sprint import build_events


@nb.njit(cache=True)
def _attempt(kind, idx, day, R, mae, n, e0, pol, a, b, c, rmin, target, daily_lim, max_loss,
             daily_guard, loss_guard, halt, max_days, max_open):
    risk = np.zeros(n)
    bal = 1.0; peak = 1.0
    cur_day = -1; day_start = 1.0; open_sum = 0.0
    d0 = day[e0]
    for e in range(e0, len(kind)):
        d = day[e]
        if d - d0 >= max_days:
            return 0, d - d0
        if d != cur_day:
            cur_day = d; day_start = bal
        i = idx[e]
        if kind[e] == 1:
            profit = bal - 1.0
            if pol == 0:
                r = a
            elif pol == 1 or pol == 5:
                r = min(max(b * (bal - (1.0 - halt)), rmin), a)
                if pol == 5 and profit >= c:
                    r = r * 0.5
            elif pol == 2:
                r = a if profit < c else b
            elif pol == 3:
                r = a * b if (peak - bal) >= c else a
            else:
                r = min(max((target - profit) / b, rmin), a)
            r = min(r, daily_guard - (day_start - bal) - open_sum, loss_guard - (1.0 - bal) - open_sum, max_open - open_sum)
            if r < rmin:
                continue
            risk[i] = r
            open_sum += r
        else:
            r = risk[i]
            if r == 0.0:
                continue
            low = bal + mae[i] * r
            if day_start - low >= daily_lim or 1.0 - low >= max_loss:
                return -1, d - d0 + 1
            bal += R[i] * r
            open_sum -= r
            risk[i] = 0.0
            if bal > peak:
                peak = bal
            if day_start - bal >= daily_lim or 1.0 - bal >= max_loss:
                return -1, d - d0 + 1
            if bal - 1.0 >= target:
                return 1, d - d0 + 1
            if 1.0 - bal >= halt and open_sum <= 1e-12:
                return -2, d - d0 + 1
    return 0, day[len(kind) - 1] - d0


@nb.njit(cache=True)
def _all(kind, idx, day, R, mae, n, starts, pol, a, b, c, rmin, target, daily_lim, max_loss, daily_guard, loss_guard, halt, max_days, max_open):
    out = np.zeros(len(starts), np.int8)
    days = np.zeros(len(starts), np.int64)
    for s in range(len(starts)):
        out[s], days[s] = _attempt(kind, idx, day, R, mae, n, starts[s], pol, a, b, c, rmin, target, daily_lim, max_loss,
                                   daily_guard, loss_guard, halt, max_days, max_open)
    return out, days


def evaluate(trades: pd.DataFrame, since: str, pol: int, a: float, b: float = 0.0, c: float = 0.0, rmin=0.0025,
             target=0.10, daily_guard=0.04, loss_guard=0.095, halt=0.08, until_margin=45, max_open=1.0) -> dict:
    p = trades[trades.t_in >= since]
    ev = build_events(p)
    kind, idx, day = ev["kind"], ev["idx"], ev["day"]
    ep = np.flatnonzero(kind == 1)
    sd = np.arange(day.min(), day.max() - until_margin)
    st = ep[np.minimum(np.searchsorted(day[ep], sd), len(ep) - 1)].astype(np.int64)
    o, d = _all(kind, idx, day, ev["R"], ev["mae"], ev["n"], st, pol, a, b, c, rmin, target, 0.05, 0.10,
                daily_guard, loss_guard, halt, 100000, max_open)
    ok = o == 1
    return {"p60": 100 * (ok & (d <= 60)).mean(), "p120": 100 * (ok & (d <= 120)).mean(), "ever": 100 * ok.mean(),
            "halt": 100 * (o == -2).mean() + 100 * (o == -1).mean(), "median": float(np.median(d[ok])) if ok.any() else np.nan}
