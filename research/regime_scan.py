"""Scan regime filters on development sets (2005-2024) and report the 2025-26 test separately."""
import numpy as np, pandas as pd
from bt import Market, run, stats
from strategies import noise_area
from final_cfg import STRAT, MGMT
from regime import daily_features, apply_filter

SETS = {"NASo": ("NAS100O", "2005-01-01", "2020-01-01", "m1o"), "SPXo": ("SPX500O", "2005-01-01", "2020-01-01", "m1o"),
        "RUTo": ("US2000O", "2005-01-01", "2020-01-01", "m1o"), "NASd": ("USATECHIDXUSD", "2019-06-01", "2026-09-01", "s10")}

def variants(f):
    T = pd.Series(True, index=f.index)
    v = {"base": (T, T)}
    for n in (20, 50, 100, 200):
        up = f[f"above_ma{n}"] == 1
        v[f"short only below MA{n}"] = (T, ~up)
        v[f"with-trend MA{n}"] = (up | f[f"above_ma{n}"].isna(), ~up)
    for p in (0.3, 0.5):
        v[f"vol_pct>{p}"] = (f.vol_pct.fillna(1) > p, f.vol_pct.fillna(1) > p)
    for p in (0.3, 0.5):
        v[f"eff_pct>{p}"] = (f.eff_pct.fillna(1) > p, f.eff_pct.fillna(1) > p)
    v["short only if dd20<-3%"] = (T, f.dd20.fillna(-1) < -0.03)
    v["long only"] = (T, T & False)
    return v

rows = []
for name, (sym, a, b, res) in SETS.items():
    m = Market(sym, "1min", start=a, end=b, exec_res=res)
    f = daily_features(m)
    for vn, (al, ash) in variants(f).items():
        it = apply_filter(m, noise_area(m, **STRAT), f, al, ash)
        tr = run(m, it, entry_same_bar_check=(res != "s10"), **MGMT)
        if name == "NASd":
            for part, (x, y) in {"NASd20-24": ("2020-01-01", "2025-01-01"), "NASd25-26": ("2025-01-01", "2027-01-01")}.items():
                t = tr[(tr.t_in >= x) & (tr.t_in < y)]
                st = stats(t); rows.append(dict(ds=part, v=vn, n=st["n"], avgR=st["avgR"], totR=st["totR"], sh=st["sharpe_d"], dd=st["maxDD_R"]))
        else:
            st = stats(tr); rows.append(dict(ds=name, v=vn, n=st["n"], avgR=st["avgR"], totR=st["totR"], sh=st["sharpe_d"], dd=st["maxDD_R"]))
    print("done", name, flush=True)
df = pd.DataFrame(rows)
df.to_csv("/tmp/data/regime_scan.csv", index=False)
pd.set_option("display.width", 250)
for col in ("sh", "avgR", "totR"):
    p = df.pivot_table(index="v", columns="ds", values=col)
    p = p[["NASo", "SPXo", "RUTo", "NASd20-24", "NASd25-26"]]
    if col == "sh":
        p["dev_min"] = p[["NASo", "SPXo", "RUTo", "NASd20-24"]].min(axis=1)
    print(f"\n== {col}\n", p.round(3).sort_values(p.columns[-1] if col == "sh" else "NASo", ascending=False).to_string())
print("\n== trades\n", df.pivot_table(index="v", columns="ds", values="n").to_string())
