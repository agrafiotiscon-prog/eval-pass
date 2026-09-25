"""Grid scan of the mean-reversion template on in-sample data."""
import itertools, sys, time
import numpy as np, pandas as pd
from bt import Market, run, stats
from strategies import mean_reversion

sym = sys.argv[1]; tf = sys.argv[2]
start, end = sys.argv[3], sys.argv[4]
m = Market(sym, tf, start=start, end=end)
sessions = {"asia": ("utc_min", 0, 360), "ldn": ("ldn_min", 480, 720), "ny_am": ("ny_min", 570, 720),
            "ny_pm": ("ny_min", 720, 960), "late": ("utc_min", 1140, 1260), "all": ("utc_min", 0, 1440)}
rows = []
t0 = time.time()
for (sname, (clk, a, b)), n, k, sl, conf in itertools.product(sessions.items(), (12, 24), (2.0, 2.5, 3.0), (1.0, 2.0, 3.0), (False, True)):
    it = mean_reversion(m, n=n, k_entry=k, sl_atr=sl, confirm=conf, clock=clk, start=a, end=b)
    tr = run(m, it, max_hold_min=int(n * pd.Timedelta(tf).total_seconds() / 60 * 2))
    st = stats(tr)
    rows.append(dict(sess=sname, n_=n, k=k, sl=sl, conf=conf, **st))
df = pd.DataFrame(rows)
print(f"{sym} {tf} {start}->{end}  ({time.time()-t0:.0f}s)")
print(df[df.n >= 150].sort_values("avgR", ascending=False).head(25).to_string())
df.to_csv(f"/tmp/data/scan_mr_{sym}_{tf}.csv", index=False)
