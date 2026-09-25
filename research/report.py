"""Regenerate the headline results (tables + charts) for the selected configuration.

Run after data_prep.py / oanda_prep.py have produced /tmp/data/{s10,m1o}.
Writes research/results/*.md and *.png.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bt import Market, run, stats, yearly
from final_cfg import MGMT, STRAT
from prop import challenge, curve_stats, equity_curve
from strategies import noise_area

OUT = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(OUT, exist_ok=True)
SETS = {
    "NAS100 Dukascopy 2020-2026 (tick bid/ask)": ("USATECHIDXUSD", "2020-01-01", "2026-09-01", "s10"),
    "NAS100 OANDA 2005-2019 (M1, 1bp spread)": ("NAS100O", "2005-01-01", "2020-01-01", "m1o"),
    "US500 OANDA 2005-2019 (M1, 1bp spread)": ("SPX500O", "2005-01-01", "2020-01-01", "m1o"),
}


def main():
    trades = {}
    lines = ["# Results for the selected configuration", "",
             f"Strategy: `{STRAT}`  ", f"Management: `{MGMT}`", ""]
    for name, (sym, a, b, res) in SETS.items():
        m = Market(sym, "1min", start=a, end=b, exec_res=res)
        tr = run(m, noise_area(m, **STRAT), entry_same_bar_check=(res != "s10"), **MGMT)
        trades[name] = tr
        st = stats(tr)
        lines += [f"## {name}", "", "| metric | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in st.items()] + [""]
        y = yearly(tr)
        lines += ["| year | trades | win % | avg R | total R | PF |", "|---|---|---|---|---|---|"]
        lines += [f"| {i} | {r.n} | {r['win%']} | {r.avgR} | {r.totR} | {r.PF} |" for i, r in y.iterrows()] + [""]

    nasd = trades[list(SETS)[0]]
    ho = nasd[nasd.t_in >= "2026-01-01"]
    lines += ["## 2026 holdout (never used for any decision)", "", f"`{stats(ho, years=0.67)}`", ""]

    port = pd.concat([trades[list(SETS)[1]], trades[list(SETS)[2]]], ignore_index=True)
    lines += ["## Prop challenge simulation", "",
              "Every calendar day is used as a start date; rules: 5 % daily loss (incl. floating), 10 % max loss, "
              "min 4 trading days, EA daily stop 3 %, 365-day window. `open` = neither passed nor failed in the window.", "",
              "| data | risk/trade | target | pass % | fail % | open % | median days | 75th pct days |",
              "|---|---|---|---|---|---|---|---|"]
    sims = [(list(SETS)[0], nasd), (list(SETS)[1], trades[list(SETS)[1]]), (list(SETS)[2], trades[list(SETS)[2]]),
            ("NAS100 + US500 together, 2005-2019", port)]
    for name, tr in sims:
        for risk in (0.005, 0.0075, 0.01):
            for tgt in (0.10, 0.08, 0.05):
                c = challenge(tr, risk=risk, target=tgt, daily_lim=0.05, max_loss=0.10, min_days=4, max_days=365, daily_stop=0.03)
                lines.append(f"| {name} | {risk*100:.2f}% | {tgt*100:.0f}% | {c['pass%']} | {c['fail%']} | {c['open%']} | {c['med_days']} | {c['p75_days']} |")
    lines += ["", "## Account curve statistics (compounded, EA daily stop 3 %)", "",
              "| data | risk/trade | CAGR % | max DD % | worst day % | worst month % | positive months % | Sharpe |",
              "|---|---|---|---|---|---|---|---|"]
    for name, tr in sims:
        for risk in (0.005, 0.0075, 0.01):
            cs = curve_stats(equity_curve(tr, risk=risk, daily_stop=0.03))
            lines.append(f"| {name} | {risk*100:.2f}% | {cs['CAGR%']} | {cs['maxDD%']} | {cs['worst_day%']} | {cs['worst_month%']} | {cs['pos_months%']} | {cs['sharpe']} |")
    open(os.path.join(OUT, "results.md"), "w").write("\n".join(lines) + "\n")

    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    for name, tr in trades.items():
        s = tr.sort_values("t_out")
        axes[0].plot(s.t_out, s.R.cumsum(), label=name, lw=1.2)
    axes[0].axvspan(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-09-01"), color="0.85", label="2026 holdout")
    axes[0].set_title("Cumulative R per trade (1R = the stop distance)")
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)
    ec = equity_curve(port, risk=0.0075, daily_stop=0.03)
    peak = np.maximum.accumulate(ec.bal.values)
    dd = (ec.bal.values / peak - 1) * 100
    axes[1].fill_between(ec.t, dd, 0, color="C3", alpha=0.5)
    axes[1].axhline(-10, color="k", ls="--", lw=0.8, label="typical prop max loss (-10 %)")
    axes[1].set_title("Drawdown from peak (%), NAS100 + US500 together, 0.75 % risk per trade, 2005-2019")
    axes[1].legend(fontsize=8); axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "equity.png"), dpi=110)
    print(open(os.path.join(OUT, "results.md")).read())


if __name__ == "__main__":
    main()
