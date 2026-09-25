"""Gold swing rules (unchanged + close neighbours) on every other market (OANDA 2005-2019)."""
import itertools, sys, gc
import numpy as np, pandas as pd
from bt import Market, run, stats
from strategies import swing_breakout
SYMS = ["OILO", "NGASO", "CORNO", "WHEATO", "SOYO", "SUGARO", "UST10O", "UST2O", "BUNDO", "GILTO", "AUDJPYO", "EURJPYO",
        "EURUSDO", "GBPUSDO", "AUDUSDO", "USDCADO", "AU200O", "NL25O", "NAS100O", "SPX500O", "US2000O", "JP225O", "UK100O", "FR40O", "XAU_O"]
rows = []
for sym in SYMS:
    m = Market(sym, "60min", start="2005-01-01", end="2020-01-01", exec_res="m1o")
    for n, sl, trl, lo in itertools.product((120, 240, 360), (2.0, 3.0), ((1.0, 1.5), (2.0, 2.0)), (False, True)):
        t = run(m, swing_breakout(m, n=n, atr_n=24, sl_atr=sl, long_only=lo), entry_same_bar_check=True, tr_trig=trl[0], tr_dist=trl[1], max_per_day=1)
        t["R"] = t.R - 0.022 * ((t.t_out.dt.normalize() - t.t_in.dt.normalize()).dt.days).clip(lower=0)
        y = t.groupby(t.t_in.dt.year).R.sum()
        st = stats(t)
        rows.append(dict(sym=sym, n=n, sl=sl, trail=f"{trl[0]}/{trl[1]}", lo=lo, trades=st["n"], sh=st["sharpe_d"], totR=st["totR"],
                         dd=st["maxDD_R"], pos_years=(y > 0).mean()))
    del m; gc.collect()
    d = pd.DataFrame([r for r in rows if r["sym"] == sym])
    print(f"{sym:8s} share>0 both-dir {(d[~d.lo].sh>0).mean():.2f} long {(d[d.lo].sh>0).mean():.2f} | median sh both {d[~d.lo].sh.median():.2f} long {d[d.lo].sh.median():.2f} | gold-cfg both {d[(d.n==240)&(d.sl==3.0)&(d.trail=='2.0/2.0')&(~d.lo)].sh.iloc[0]:.2f}", flush=True)
pd.DataFrame(rows).to_csv("/tmp/data/swing_scan.csv", index=False)
