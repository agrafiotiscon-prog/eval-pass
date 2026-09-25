"""Per-config yearly robustness summary for one family of one instrument (wf grid output)."""
import sys
import numpy as np, pandas as pd
from wf import OUT
sym, fam = sys.argv[1], sys.argv[2]
dev_end = 2025
tr = pd.read_parquet(f"{OUT}/{sym}_trades.parquet"); meta = pd.read_parquet(f"{OUT}/{sym}_meta.parquet")
tr = tr.merge(meta[["cfg", "fam", "params", "mgmt"]], on="cfg"); tr = tr[tr.fam == fam]
if fam == "swing":
    nights = ((tr.t_out.dt.normalize() - tr.t_in.dt.normalize()).dt.days).clip(lower=0)
    tr = tr.assign(R=tr.R - 0.022 * nights)            # overnight financing estimate
g = tr.groupby(["cfg", tr.t_in.dt.year]).R.sum().unstack().fillna(0)
years = [y for y in g.columns if y < dev_end]
d = tr[tr.t_in.dt.year < dev_end].groupby(["cfg", tr.t_in.dt.normalize()]).R.sum()
sh = d.groupby(level=0).apply(lambda s: s.mean() / s.std() * np.sqrt(252))
d2 = tr[tr.t_in.dt.year >= dev_end].groupby(["cfg", tr.t_in.dt.normalize()]).R.sum()
sh2 = d2.groupby(level=0).apply(lambda s: s.mean() / s.std() * np.sqrt(252))
s = pd.DataFrame({"sh_dev": sh, "pos_years": (g[years] > 0).sum(axis=1), "n_years": len(years), "worst_year": g[years].min(axis=1),
                  "tot_dev": g[years].sum(axis=1), "R2025": g.get(2025, 0), "R2026": g.get(2026, 0), "sh_25_26": sh2,
                  "trades_per_yr": tr.groupby("cfg").size() / (len(g.columns))}).join(meta.set_index("cfg")[["params", "mgmt"]])
pd.set_option("display.width", 320); pd.set_option("display.max_colwidth", 150)
print(f"{sym} {fam}: {len(s)} configs | share sh_dev>0: {(s.sh_dev>0).mean():.2f} | share 2025-26 positive: {((s.R2025+s.R2026)>0).mean():.2f} | median sh_dev {s.sh_dev.median():.2f} | median sh_25_26 {s.sh_25_26.median():.2f}")
print(s.sort_values("sh_dev", ascending=False).head(int(sys.argv[3]) if len(sys.argv) > 3 else 15).round(2).to_string())
