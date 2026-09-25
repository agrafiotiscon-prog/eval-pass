"""Per-market strategy results + portfolio prop simulations -> research/results/portfolio.md

Needs: /tmp/data/m1 (Dukascopy M1 2012/13-2026 for USATECHIDXUSD, XAUUSD, ...), /tmp/data/m1o (OANDA
2005-2019) and, for the walk-forward table, /tmp/data/wf/*_trades.parquet from wf.py.
"""
import os

import numpy as np
import pandas as pd

from bt import Market, run, stats
from final_cfg import MGMT, STRAT
from sprint import _run_all, build_events
from strategies import noise_area, swing_breakout
from wf import OUT as WF_OUT
from wf import walk_forward

RES = os.path.join(os.path.dirname(__file__), "results")
TOKYO = dict(clock="utc_min", open_min=0, close_min=360, first_check=30, last_entry=330, flat_min=355)
GOLD = dict(n=240, atr_n=24, sl_atr=3.0, trend_n=0, long_only=False)
GOLD_MG = dict(tr_trig=2.0, tr_dist=2.0, max_per_day=1)
SWAP_R_PER_NIGHT = 0.022
C = ["t_in", "t_out", "R", "mae"]


def momentum(sym, a, b, res, sess=None):
    m = Market(sym, "1min", start=a, end=b, exec_res=res)
    return run(m, noise_area(m, **STRAT, **(sess or {})), entry_same_bar_check=(res != "s10"), **MGMT)


def gold(sym, a, b, res):
    m = Market(sym, "60min", start=a, end=b, exec_res=res)
    t = run(m, swing_breakout(m, **GOLD), entry_same_bar_check=(res != "s10"), **GOLD_MG)
    t["R"] = t.R - SWAP_R_PER_NIGHT * ((t.t_out.dt.normalize() - t.t_in.dt.normalize()).dt.days).clip(lower=0)
    return t


def sim(p, pol, r, since, dg):
    p = p[p.t_in >= since]
    ev = build_events(p)
    kind, idx, day = ev["kind"], ev["idx"], ev["day"]
    ep = np.flatnonzero(kind == 1)
    sd = np.arange(day.min(), day.max() - 45)
    st = ep[np.minimum(np.searchsorted(day[ep], sd), len(ep) - 1)].astype(np.int64)
    s, d, _, _, _ = _run_all(kind, idx, day, ev["R"], ev["mae"], ev["n"], st, pol, r, 0.0025, 2.5, 0.10, 0.05, 0.10, dg, 0.095, 0, 3650, 1, 0.08)
    ok = s == 1
    f = lambda x: f"{x:.0f}%"
    return [f(100 * (ok & (d <= 60)).mean()), f(100 * (ok & (d <= 120)).mean()), f(100 * ok.mean()), f(100 * (s == -2).mean()),
            f"{np.median(d[ok]):.0f}" if ok.any() else "-"]


def main():
    L = ["# Per-market strategies and portfolio", ""]
    # ---- walk-forward by family
    L += ["## Walk-forward by strategy family (3-year train, 6-month blind test, 2015/16-2026)", "",
          "| market | family | blind trades/yr | blind Sharpe | blind total R | R 2025-26 |", "|---|---|---|---|---|---|"]
    for sym in ("USATECHIDXUSD", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"):
        path = f"{WF_OUT}/{sym}_trades.parquet"
        if not os.path.exists(path):
            continue
        tr = pd.read_parquet(path).merge(pd.read_parquet(f"{WF_OUT}/{sym}_meta.parquet")[["cfg", "fam"]], on="cfg")
        for fam in ("noise", "orb", "bo", "mr", "swing"):
            oos, _ = walk_forward(tr, first_test="2016-01-01", top_k=1, families=[fam])
            if len(oos) == 0:
                continue
            st = stats(oos)
            r2526 = oos[oos.t_in >= "2025-01-01"].R.sum()
            L.append(f"| {sym} | {fam} | {st['per_yr']} | {st['sharpe_d']} | {st['totR']} | {r2526:.1f} |")
    # ---- fixed strategy per market
    L += ["", "## Fixed strategy per market", "",
          "| market / data | strategy | trades | avg R | PF | Sharpe | max DD (R) | profitable years | R 2025-26 |",
          "|---|---|---|---|---|---|---|---|---|"]
    T = {
        "NDX100 Dukascopy 2013-26": ("momentum", momentum("USATECHIDXUSD", "2013-01-01", "2026-09-01", "m1")),
        "NDX100 OANDA 2005-19": ("momentum", momentum("NAS100O", "2005-01-01", "2020-01-01", "m1o")),
        "SPX500 OANDA 2005-19": ("momentum", momentum("SPX500O", "2005-01-01", "2020-01-01", "m1o")),
        "JP225 OANDA 2010-19": ("momentum (Tokyo)", momentum("JP225O", "2005-01-01", "2020-01-01", "m1o", TOKYO)),
        "XAUUSD Dukascopy 2012-26": ("swing long+short", gold("XAUUSD", "2012-01-01", "2026-09-01", "m1")),
        "XAUUSD OANDA 2006-19": ("swing long+short", gold("XAU_O", "2006-01-01", "2020-01-01", "m1o")),
    }
    for name, (strat, t) in T.items():
        st = stats(t)
        y = t.groupby(t.t_in.dt.year).R.sum()
        r2526 = t[t.t_in >= "2025-01-01"].R.sum() if t.t_in.max() >= pd.Timestamp("2025-01-01") else float("nan")
        L.append(f"| {name} | {strat} | {st['n']} | {st['avgR']} | {st['PF']} | {st['sharpe_d']} | {st['maxDD_R']} | {(y > 0).sum()}/{len(y)} | {r2526:.1f} |")
    # ---- portfolios
    idx10 = pd.concat([T[k][1][C] for k in ("NDX100 OANDA 2005-19", "SPX500 OANDA 2005-19", "JP225 OANDA 2010-19")])
    g10 = T["XAUUSD OANDA 2006-19"][1][C]
    nas20 = T["NDX100 Dukascopy 2013-26"][1][C]
    g20 = T["XAUUSD Dukascopy 2012-26"][1][C]
    P = [("3 indices momentum", idx10, "2010-01-01"), ("3 indices + gold swing", pd.concat([idx10, g10]), "2010-01-01"),
         ("NDX100 momentum", nas20, "2020-01-01"), ("NDX100 + gold swing", pd.concat([nas20, g20]), "2020-01-01"),
         ("NDX100 momentum", nas20, "2025-01-01"), ("NDX100 + gold swing", pd.concat([nas20, g20]), "2025-01-01")]
    L += ["", "## Prop challenge simulation (one attempt; +10 % target, 5 % daily, 10 % max, EA halt at -8 %)", "",
          "| markets | start dates | risk per trade | pass <= 60 d | pass <= 120 d | pass eventually | halted | median days |",
          "|---|---|---|---|---|---|---|---|"]
    for name, p, since in P:
        for lab, pol, r, dg in (("0.5 %", 0, 0.005, 0.03), ("0.75 %", 0, 0.0075, 0.03), ("1.0 %", 0, 0.01, 0.04), ("Sprint", 1, 0.04, 0.04)):
            L.append(f"| {name} | from {since[:4]} | {lab} | " + " | ".join(sim(p, pol, r, since, dg)) + " |")
    L += ["", "Markets without a robust edge in these tests: EURUSD, GBPUSD, USDJPY (long-only trend = past drift, "
          "lost in 2025-26), XAGUSD and BTCUSD (gold swing settings unprofitable), UK100 and FR40 (momentum weak)."]
    open(os.path.join(RES, "portfolio.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
