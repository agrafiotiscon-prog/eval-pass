"""Robustness grid (corrected exit encoding) incl. exit rule, target and break-even."""
import itertools, pandas as pd, numpy as np
from bt import Market, run, stats
from strategies import noise_area
sets = {"NASd": ("USATECHIDXUSD", "2020-01-01", "2026-01-01", "s10"),
        "NASo": ("NAS100O", "2005-01-01", "2020-01-01", "m1o"),
        "SPXo": ("SPX500O", "2005-01-01", "2020-01-01", "m1o")}
stops = [("sig", 0.75), ("sig", 1.0), ("sig", 1.5), ("band", 0.0)]
exits = [("band", True), ("band", False), ("none", False)]
allres = []
for name, (sym, a, b, res) in sets.items():
    m = Market(sym, "1min", start=a, end=b, exec_res=res)
    for lb, ce, vm, (slm, sls), (em, vw), tp, be in itertools.product((20, 30), (30, 60), (1.5, 2.0), stops, exits, (0.0, 2.5), (0.0, 1.5)):
        it = noise_area(m, lookback=lb, check_every=ce, vol_mult=vm, sl_mode=slm, sl_sigma=sls or 1.0,
                        use_vwap=vw, exit_mode=em, tp_r=tp)
        kw = dict(be_trig=be, be_off=0.1) if be else {}
        tr = run(m, it, max_per_day=3, entry_same_bar_check=(res != "s10"), **kw)
        allres.append(dict(ds=name, lb=lb, ce=ce, vm=vm, slm=slm, sls=sls, exit=em, vwap=vw, tp=tp, be=be, **stats(tr)))
    print("done", name, flush=True)
pd.DataFrame(allres).to_csv("/tmp/data/robust_grid.csv", index=False)
