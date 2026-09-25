"""Grid scan of the breakout template on in-sample data."""
import itertools, sys, time
import numpy as np, pandas as pd
from bt import Market, run, stats
from strategies import breakout

sym = sys.argv[1]; tf = sys.argv[2]
start, end = sys.argv[3], sys.argv[4]
m = Market(sym, tf, start=start, end=end)
sessions = {"asia": ("utc_min", 0, 360), "ldn": ("ldn_min", 420, 660), "ny_am": ("ny_min", 540, 720),
            "ny_pm": ("ny_min", 720, 960), "ldn_ny": ("ldn_min", 420, 1020)}
rows = []
t0 = time.time()
for (sname, (clk, a, b)), n, sl, (tr_trig, tr_dist), tnd in itertools.product(
        sessions.items(), (12, 24, 48), (1.0, 2.0), ((0, 0), (1.0, 1.0), (2.0, 1.5)), (0, 100)):
    it = breakout(m, n=n, sl_atr=sl, clock=clk, start=a, end=b, trend_n=tnd, tp_r=0 if tr_trig else 2.0)
    # flatten at session end
    s = m.sig; c = s[clk].values
    it.ex[~((c >= a) & (c < b + 120))] = 2
    tr = run(m, it, tr_trig=tr_trig, tr_dist=tr_dist)
    st = stats(tr)
    rows.append(dict(sess=sname, n_=n, sl=sl, trail=f"{tr_trig}/{tr_dist}", trend=tnd, **st))
df = pd.DataFrame(rows)
print(f"{sym} {tf} {start}->{end}  ({time.time()-t0:.0f}s)")
print(df[df.n >= 150].sort_values("avgR", ascending=False).head(25).to_string())
df.to_csv(f"/tmp/data/scan_bo_{sym}_{tf}.csv", index=False)
