"""Convert OANDA mid-price M1 CSVs (FutureSharks/financial-data) to the bid/ask bar schema
with a synthetic spread of `spread_bp` basis points of price."""
import glob, sys
import pandas as pd

src, sym, out, spread_bp = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
files = glob.glob(f"{src}/**/*.csv", recursive=True)
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
df["time"] = pd.to_datetime(df.time)
df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
half = df.close * spread_bp * 1e-4 / 2
out_df = pd.DataFrame({
    "time": df.time,
    "bo": df.open - half, "bh": df.high - half, "bl": df.low - half, "bc": df.close - half,
    "ao": df.open + half, "ah": df.high + half, "al": df.low + half, "ac": df.close + half,
    "n": df.volume.astype("uint32"), "spr": 2 * half, "sprmax": 2 * half,
})
for y, g in out_df.groupby(out_df.time.dt.year):
    g.to_parquet(f"{out}/{sym}-{y}.parquet", index=False)
print(sym, len(out_df), out_df.time.min(), out_df.time.max())
