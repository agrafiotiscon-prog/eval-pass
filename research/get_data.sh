#!/usr/bin/env bash
# Rebuild the research datasets under /tmp/data (about 6 GB of downloads).
#  * Dukascopy tick data (bid/ask) published as GitHub releases by esmaeil999/*
#  * OANDA M1 mid prices 2005-2020 from FutureSharks/financial-data
set -euo pipefail
D=/tmp/data
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$D/s10" "$D/m1" "$D/m1o"

fetch() {  # repo symbol
  mkdir -p "$D/$2"
  for y in 2020 2021 2022 2023 2024 2025 2026; do
    f="$D/$2/ticks-$2-$y.zip"
    [ -s "$f" ] || curl -sSL --retry 4 -o "$f" "https://github.com/esmaeil999/$1/releases/download/ticks-$2-$y/ticks-$2-$y.zip"
  done
  python3 "$HERE/data_prep.py" "$D/$2" "$D/s10" 10s
  python3 "$HERE/data_prep.py" "$D/$2" "$D/m1" 1m
}
fetch USA-100-Technical-Index USATECHIDXUSD
# optional, used in the scalping scans that did not make the cut:
# fetch xauusd XAUUSD; fetch eurusd EURUSD; fetch gbpusd GBPUSD; fetch usdjpy USDJPY

if [ ! -d "$D/financial-data" ]; then
  git clone -q --filter=blob:none --no-checkout --depth 1 https://github.com/FutureSharks/financial-data "$D/financial-data"
  (cd "$D/financial-data" && git sparse-checkout init --no-cone && \
   git sparse-checkout set 'pyfinancialdata/data/currencies/oanda/NAS100_USD/' 'pyfinancialdata/data/currencies/oanda/SPX500_USD/' \
     'pyfinancialdata/data/currencies/oanda/US2000_USD/' 'pyfinancialdata/data/currencies/oanda/JP225_USD/' && \
   git checkout -q HEAD)
fi
O="$D/financial-data/pyfinancialdata/data/currencies/oanda"
python3 "$HERE/oanda_prep.py" "$O/NAS100_USD" NAS100O "$D/m1o" 1.0
python3 "$HERE/oanda_prep.py" "$O/SPX500_USD" SPX500O "$D/m1o" 1.0
python3 "$HERE/oanda_prep.py" "$O/US2000_USD" US2000O "$D/m1o" 1.0     # sprint-mode markets
python3 "$HERE/oanda_prep.py" "$O/JP225_USD" JP225O "$D/m1o" 1.0

# per-market research (wf.py): Dukascopy M1 2012-2026 for gold and FX, OANDA gold 2006-2019
for spec in "USA-100-Technical-Index:USATECHIDXUSD" "xauusd:XAUUSD" "eurusd:EURUSD" "gbpusd:GBPUSD" "usdjpy:USDJPY"; do
  repo=${spec%%:*}; sym=${spec##*:}
  mkdir -p "$D/dl"
  for y in 2012 2013 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026; do
    [ -f "$D/m1/$sym-$y.parquet" ] && continue
    curl -sSfL --retry 4 -o "$D/dl/ticks-$sym-$y.zip" "https://github.com/esmaeil999/$repo/releases/download/ticks-$sym-$y/ticks-$sym-$y.zip" || continue
    python3 "$HERE/data_prep.py" "$D/dl" "$D/m1" 1m && rm -f "$D/dl/ticks-$sym-$y.zip"
  done
done
(cd "$D/financial-data" && git sparse-checkout add 'pyfinancialdata/data/currencies/oanda/XAU_USD/' && git checkout -q HEAD)
python3 "$HERE/oanda_prep.py" "$O/XAU_USD" XAU_O "$D/m1o" 2.0
