"""Convert Dukascopy tick CSV exports (zipped) into bid/ask bars.

Usage: python data_prep.py <zip_dir> <out_dir> [every]   (every defaults to 1m; e.g. 10s)
Output: one parquet per input zip with columns
  time (bar open, UTC), bo bh bl bc (bid OHLC), ao ah al ac (ask OHLC),
  n (tick count), spr (mean spread), sprmax (max spread)
"""
import os
import subprocess
import sys

import polars as pl


def convert(zip_path: str, out_path: str, tmp_dir: str, every: str = "1m") -> None:
    if zip_path.endswith(".gz"):
        csv_path = os.path.join(tmp_dir, os.path.basename(zip_path)[:-3])
        with open(csv_path, "wb") as fo:
            subprocess.run(["gzip", "-dc", zip_path], stdout=fo, check=True)
    else:
        csv_name = subprocess.run(["unzip", "-Z1", zip_path], capture_output=True, text=True, check=True).stdout.split()[0]
        subprocess.run(["unzip", "-o", "-q", zip_path, csv_name, "-d", tmp_dir], check=True)
        csv_path = os.path.join(tmp_dir, csv_name)
    try:
        df = pl.read_csv(
            csv_path,
            columns=["GmtTime", "Bid", "Ask"],
            schema_overrides={"GmtTime": pl.Utf8, "Bid": pl.Float64, "Ask": pl.Float64},
        )
        df = df.with_columns(pl.col("GmtTime").str.to_datetime("%Y-%m-%d %H:%M:%S%.3f", time_unit="ms").alias("t")).drop("GmtTime")
        df = df.filter(pl.col("Ask") >= pl.col("Bid")).sort("t")
        bars = (
            df.group_by_dynamic("t", every=every, label="left")
            .agg(
                bo=pl.col("Bid").first(), bh=pl.col("Bid").max(), bl=pl.col("Bid").min(), bc=pl.col("Bid").last(),
                ao=pl.col("Ask").first(), ah=pl.col("Ask").max(), al=pl.col("Ask").min(), ac=pl.col("Ask").last(),
                n=pl.len(),
                spr=(pl.col("Ask") - pl.col("Bid")).mean(),
                sprmax=(pl.col("Ask") - pl.col("Bid")).max(),
            )
            .rename({"t": "time"})
        )
        bars.write_parquet(out_path)
        print(f"{os.path.basename(zip_path)}: {len(df):,} ticks -> {len(bars):,} bars", flush=True)
    finally:
        os.remove(csv_path)


def main() -> None:
    zip_dir, out_dir = sys.argv[1], sys.argv[2]
    every = sys.argv[3] if len(sys.argv) > 3 else "1m"
    tmp_dir = os.path.join(out_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    for name in sorted(os.listdir(zip_dir)):
        if not (name.endswith(".zip") or name.endswith(".csv.gz")):
            continue
        out_path = os.path.join(out_dir, name.replace("ticks-", "").replace(".zip", ".parquet").replace(".csv.gz", ".parquet"))
        if os.path.exists(out_path):
            continue
        convert(os.path.join(zip_dir, name), out_path, tmp_dir, every)


if __name__ == "__main__":
    main()
