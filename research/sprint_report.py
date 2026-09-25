"""Regenerate the Sprint-mode numbers (research/results/sprint.md).

Needs /tmp/data/s10 (NAS100 Dukascopy) and /tmp/data/m1o (OANDA NAS100, US500, US2000, JP225),
see get_data.sh. Uses the same strategy settings as the standard mode; only sizing differs.
"""
import os

import numpy as np
import pandas as pd

from bt import Market, run
from final_cfg import MGMT, STRAT
from prop import challenge
from sprint import _run_all, build_events
from strategies import noise_area

OUT = os.path.join(os.path.dirname(__file__), "results")
NY = dict(clock="ny_min", open_min=570, close_min=960, first_check=600, last_entry=930, flat_min=955)
TOKYO = dict(clock="utc_min", open_min=0, close_min=360, first_check=30, last_entry=330, flat_min=355)
SPRINT = dict(policy=1, r_max=0.04, r_min=0.0025, k=2.5, target=0.10, daily_lim=0.05, max_loss=0.10,
              daily_guard=0.04, loss_guard=0.095, halt_dd=0.08)


def trades(sym, start, end, res, sess):
    m = Market(sym, "1min", start=start, end=end, exec_res=res)
    return run(m, noise_area(m, **STRAT, **sess), entry_same_bar_check=(res != "s10"), **MGMT)


def sprint_row(p):
    ev = build_events(p)
    kind, idx, day = ev["kind"], ev["idx"], ev["day"]
    entry_pos = np.flatnonzero(kind == 1)
    start_days = np.arange(day.min(), day.max() - 30)
    starts = entry_pos[np.minimum(np.searchsorted(day[entry_pos], start_days), len(entry_pos) - 1)]
    single, sdays, funded, att, _ = _run_all(kind, idx, day, ev["R"], ev["mae"], ev["n"], starts.astype(np.int64),
                                             SPRINT["policy"], SPRINT["r_max"], SPRINT["r_min"], SPRINT["k"],
                                             SPRINT["target"], SPRINT["daily_lim"], SPRINT["max_loss"],
                                             SPRINT["daily_guard"], SPRINT["loss_guard"], 0, 30, 730, SPRINT["halt_dd"])
    ok = single == 1
    okf = funded > 0
    return {"pass <= 7 days %": round(100 * (ok & (sdays <= 7)).mean(), 1),
            "pass <= 14 days %": round(100 * (ok & (sdays <= 14)).mean(), 1),
            "pass <= 30 days %": round(100 * (ok & (sdays <= 30)).mean(), 1),
            "halted at -8 % within 30 days %": round(100 * (single == -2).mean(), 1),
            "median days to funded (free restarts)": float(np.median(funded[okf])),
            "75th pct days to funded": float(np.percentile(funded[okf], 75)),
            "average attempts": round(float(att[okf].mean()), 2)}


def main():
    nas = trades("NAS100O", "2005-01-01", "2020-01-01", "m1o", NY)
    spx = trades("SPX500O", "2005-01-01", "2020-01-01", "m1o", NY)
    rut = trades("US2000O", "2005-01-01", "2020-01-01", "m1o", NY)
    jpn = trades("JP225O", "2005-01-01", "2020-01-01", "m1o", TOKYO)
    nasd = trades("USATECHIDXUSD", "2020-01-01", "2026-09-01", "s10", NY)
    since10 = lambda t: t[t.t_in >= "2010-01-01"]
    ports = {"NAS100 + US500 (2005-19)": pd.concat([nas, spx]),
             "NAS100 + US500 + US2000 (2005-19)": pd.concat([nas, spx, rut]),
             "NAS100 + US500 + US2000 + JP225 (2010-19)": pd.concat([since10(nas), since10(spx), since10(rut), since10(jpn)]),
             "NAS100 only (Dukascopy 2020-26)": nasd}
    table = pd.DataFrame({k: sprint_row(p) for k, p in ports.items()})
    lines = ["# Sprint mode results", "",
             "Sizing: risk = (target - profit) / 2.5 per trade, capped at 4 % of the initial balance and by the room left "
             "before a 4 % worst-case daily loss / 9.5 % worst-case total loss (open stops included). The attempt is "
             "abandoned (EA halts) at -8 %; 'free restarts' starts a new challenge the next day. Every calendar day is a "
             "start date. With a 4-trading-day minimum and the helper enabled the pass rates are unchanged.", "",
             table.to_markdown(), "",
             "## Standard sizing on more markets (reference)", "",
             "| markets | risk/trade | pass % | fail % | open % | median days |", "|---|---|---|---|---|---|"]
    for name in ("NAS100 + US500 + US2000 (2005-19)", "NAS100 + US500 + US2000 + JP225 (2010-19)"):
        for r in (0.005, 0.0075):
            c = challenge(ports[name], risk=r, daily_stop=0.03, min_days=4, max_days=365)
            lines.append(f"| {name} | {r*100:.2f}% | {c['pass%']} | {c['fail%']} | {c['open%']} | {c['med_days']} |")
    for name, t in (("US2000 (2005-19)", rut), ("JP225 (2005-19 data, trades from 2010)", jpn)):
        y = t.groupby(t.t_in.dt.year).R.sum()
        lines.append(f"\n{name}: {len(t)} trades, avg R {t.R.mean():.3f}, profitable years {(y > 0).sum()}/{len(y)}")
    open(os.path.join(OUT, "sprint.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
