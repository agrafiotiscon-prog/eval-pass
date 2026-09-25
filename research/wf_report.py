"""Walk-forward report for one instrument (needs wf.py output)."""
import sys

import numpy as np
import pandas as pd

from bt import Market, run, stats
from final_cfg import STRAT, MGMT
from strategies import noise_area
from wf import OUT, walk_forward


def wstats(t: pd.DataFrame, years=None) -> dict:
    if len(t) == 0:
        return {"n": 0}
    t = t.assign(R=t.R * t.w, mae=t.mae * t.w)
    return stats(t, years)


def yearly_R(t: pd.DataFrame) -> dict:
    return (t.R * t.w).groupby(t.t_in.dt.year).sum().round(1).to_dict()


def load(sym):
    tr = pd.read_parquet(f"{OUT}/{sym}_trades.parquet")
    meta = pd.read_parquet(f"{OUT}/{sym}_meta.parquet")
    return tr.merge(meta[["cfg", "fam"]], on="cfg"), meta


def report(sym, first_test="2016-01-01", current=True):
    tr, meta = load(sym)
    rows, yearly = [], {}
    modes = {"WF top1 (all families)": dict(top_k=1), "WF top3 (all families)": dict(top_k=3), "WF top5 (all families)": dict(top_k=5)}
    for fam in sorted(tr.fam.unique()):
        modes[f"WF top1 {fam} only"] = dict(top_k=1, families=[fam])
        modes[f"WF top3 {fam} only"] = dict(top_k=3, families=[fam])
    picks_all = {}
    for name, kw in modes.items():
        oos, picks = walk_forward(tr, first_test=first_test, **kw)
        picks_all[name] = picks
        st = wstats(oos)
        rec = wstats(oos[oos.t_in >= "2025-01-01"], years=1.67)
        rows.append(dict(mode=name, **{k: st.get(k) for k in ("n", "per_yr", "avgR", "PF", "totR", "maxDD_R", "sharpe_d")},
                         R_2025_26=rec.get("totR"), sh_2025_26=rec.get("sharpe_d")))
        yearly[name] = yearly_R(oos)
    if current and sym == "USATECHIDXUSD":
        m = Market(sym, "1min", start="2013-01-01", end="2026-09-01", exec_res="m1")
        cur = run(m, noise_area(m, **STRAT), entry_same_bar_check=True, **MGMT).assign(w=1.0)
        cur = cur[cur.t_in >= first_test]
        st = wstats(cur); rec = wstats(cur[cur.t_in >= "2025-01-01"], years=1.67)
        rows.append(dict(mode="CURRENT EA (fixed)", **{k: st.get(k) for k in ("n", "per_yr", "avgR", "PF", "totR", "maxDD_R", "sharpe_d")},
                         R_2025_26=rec.get("totR"), sh_2025_26=rec.get("sharpe_d")))
        yearly["CURRENT EA (fixed)"] = yearly_R(cur)
    df = pd.DataFrame(rows).sort_values("sharpe_d", ascending=False)
    pd.set_option("display.width", 250)
    print(f"===== {sym}: walk-forward out-of-sample from {first_test} (3y train, 6m test)")
    print(df.to_string(index=False))
    print(pd.DataFrame(yearly).T.loc[df["mode"]].to_string())
    return df, picks_all, tr, meta


if __name__ == "__main__":
    report(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "2016-01-01")
