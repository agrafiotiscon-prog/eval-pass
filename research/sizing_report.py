"""Sizing-policy comparison on the index-momentum + gold-swing portfolios -> results/sizing.md

Needs trade lists written by the research scripts (see README): OANDA indices 2005-19, gold 2006-19,
Dukascopy NDX100 2013-26 and gold 2012-26.
"""
import os

import pandas as pd

from sizing import evaluate

RES = os.path.join(os.path.dirname(__file__), "results")
C = ["t_in", "t_out", "R", "mae"]


def main():
    idx10 = pd.concat([pd.read_parquet(f"/tmp/data/trades_A_{k}.parquet")[C] for k in ("NASo", "SPXo", "JP225O")])
    g10 = pd.read_parquet("/tmp/data/trades_gold_oanda_both.parquet")[C]
    nas = pd.read_parquet("/tmp/data/trades_nas_m1.parquet")[C]
    gold = pd.read_parquet("/tmp/data/trades_gold_both.parquet")[C]
    tests = [("3 indices + gold, 2010-19", pd.concat([idx10, g10]), "2010-01-01"),
             ("NDX100 + gold, 2020-26", pd.concat([nas, gold]), "2020-01-01"),
             ("NDX100 + gold, starts 2025-26", pd.concat([nas, gold]), "2025-01-01")]
    pols = [("fixed 0.5 %", 0, 0.005, 0, 0), ("fixed 0.75 %", 0, 0.0075, 0, 0), ("fixed 1.0 %", 0, 0.01, 0, 0),
            ("cushion x0.10, max 2 %", 1, 0.02, 0.10, 0), ("**cushion x0.15, max 2 %**", 1, 0.02, 0.15, 0),
            ("cushion x0.15, max 1.5 %", 1, 0.015, 0.15, 0), ("cushion x0.20, max 2 %", 1, 0.02, 0.20, 0),
            ("step 0.75 % -> 1.2 % after +2 %", 2, 0.0075, 0.012, 0.02), ("half risk in a 3 % drawdown (1 %)", 3, 0.01, 0.5, 0.03),
            ("sprint (target-based, max 4 %)", 4, 0.04, 2.5, 0)]
    L = ["# Position-sizing policies (one challenge attempt: +10 % target, 5 % daily, 10 % max, EA halt at -8 %)", "",
         "Cushion = balance minus the -8 % halt level (8 % at the start). Risk per trade = multiplier x cushion,",
         "capped; all policies are also capped by the 4 % daily / 9.5 % total worst-case budget (open stops included).", ""]
    for tn, P, since in tests:
        L += [f"## {tn}", "", "| policy | pass <= 120 d | pass eventually | halted | median days |", "|---|---|---|---|---|"]
        for name, pol, a, b, c in pols:
            r = evaluate(P, since, pol, a, b, c)
            L.append(f"| {name} | {r['p120']:.0f} % | {r['ever']:.0f} % | {r['halt']:.0f} % | {r['median']:.0f} |")
        L.append("")
    L += ["Rejected: capping total open risk (lowers pass rates, halts unchanged); giving gold more risk than an",
          "index (x1.5-2 raises halts to 8-14 % in 2010-19)."]
    open(os.path.join(RES, "sizing.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
