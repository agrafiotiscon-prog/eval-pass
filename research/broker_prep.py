"""Convert CSVs written by mt5/Scripts/ExportSessionBars.mq5 into the bid/ask bar schema (UTC).

Usage: python broker_prep.py <folder with export_*.csv> [out_dir=/tmp/data/m1b] [winter_gmt=2] [dst=us]
Broker bars are Bid; ask = bid + spread_points * point. Server time is converted to UTC with the
usual "GMT+2 winter / GMT+3 during US daylight saving" rule unless told otherwise.
"""
import glob
import os
import re
import sys

import pandas as pd


def server_to_utc(t: pd.Series, winter: int, dst: str) -> pd.Series:
    approx = t - pd.Timedelta(hours=winter)
    if dst == "us":
        ny = approx.dt.tz_localize("UTC").dt.tz_convert("America/New_York")
        is_dst = ny.map(lambda x: bool(x.dst()))
    elif dst == "eu":
        eu = approx.dt.tz_localize("UTC").dt.tz_convert("Europe/London")
        is_dst = eu.map(lambda x: bool(x.dst()))
    else:
        is_dst = pd.Series(False, index=t.index)
    return approx - pd.to_timedelta(is_dst.astype(int), unit="h")


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/data/m1b"
    winter = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    dst = sys.argv[4] if len(sys.argv) > 4 else "us"
    os.makedirs(out, exist_ok=True)
    for fn in sorted(glob.glob(os.path.join(src, "export_*.csv"))):
        m = re.match(r"export_(.+)_(\d{4})\.csv", os.path.basename(fn))
        sym, year = m.group(1), m.group(2)
        raw = open(fn).read().splitlines()[1:3]
        decimals = max(len(x.split(",")[1].split(".")[1]) if "." in x.split(",")[1] else 0 for x in raw)
        point = 10.0 ** (-decimals)
        df = pd.read_csv(fn)
        t = server_to_utc(pd.to_datetime(df.time, unit="s"), winter, dst)
        spr = df.spread_points * point
        bars = pd.DataFrame({"time": t, "bo": df.open, "bh": df.high, "bl": df.low, "bc": df.close,
                             "ao": df.open + spr, "ah": df.high + spr, "al": df.low + spr, "ac": df.close + spr,
                             "n": df.tick_volume.astype("uint32"), "spr": spr, "sprmax": spr})
        path = os.path.join(out, f"{sym}B-{year}.parquet")
        bars.to_parquet(path, index=False)
        print(f"{sym} {year}: {len(bars):,} bars, point {point}, median spread {spr.median():.4g}")


if __name__ == "__main__":
    main()
