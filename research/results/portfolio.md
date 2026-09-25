# Per-market strategies and portfolio

## Walk-forward by strategy family (3-year train, 6-month blind test, 2015/16-2026)

| market | family | blind trades/yr | blind Sharpe | blind total R | R 2025-26 |
|---|---|---|---|---|---|
| USATECHIDXUSD | noise | 123.0 | 1.92 | 152.5 | -4.1 |
| USATECHIDXUSD | orb | 174.6 | 0.65 | 76.4 | 6.6 |
| USATECHIDXUSD | bo | 352.4 | 0.92 | 236.8 | 24.0 |
| USATECHIDXUSD | mr | 15.2 | -4.9 | -23.6 | -4.3 |
| USATECHIDXUSD | swing | 61.3 | 1.88 | 117.1 | -9.4 |
| XAUUSD | noise | 103.0 | -1.34 | -80.6 | -35.5 |
| XAUUSD | orb | 209.6 | -0.23 | -50.4 | -3.4 |
| XAUUSD | bo | 114.9 | -1.16 | -99.3 | -8.0 |
| XAUUSD | mr | 28.6 | -1.33 | -16.3 | 0.0 |
| XAUUSD | swing | 51.0 | 1.98 | 104.7 | 37.2 |
| EURUSD | noise | 120.1 | -0.24 | -17.1 | -2.2 |
| EURUSD | orb | 221.7 | -0.06 | -12.8 | 8.7 |
| EURUSD | bo | 431.2 | -0.08 | -21.1 | -24.6 |
| EURUSD | mr | 154.6 | 0.3 | 22.2 | -0.5 |
| EURUSD | swing | 100.2 | -0.44 | -41.4 | -12.9 |
| GBPUSD | noise | 115.7 | -0.15 | -11.2 | 8.2 |
| GBPUSD | orb | 221.3 | 0.11 | 26.4 | 27.2 |
| GBPUSD | bo | 511.1 | -0.03 | -7.1 | 0.0 |
| GBPUSD | mr | 72.0 | -1.79 | -67.7 | -15.7 |
| GBPUSD | swing | 70.9 | -0.63 | -43.3 | -30.2 |
| USDJPY | noise | 136.2 | 0.43 | 35.8 | 4.0 |
| USDJPY | orb | 202.6 | 0.49 | 115.8 | 71.1 |
| USDJPY | bo | 424.6 | 0.31 | 95.8 | 26.3 |
| USDJPY | mr | 96.1 | -0.94 | -46.9 | -11.6 |
| USDJPY | swing | 80.7 | 0.71 | 61.7 | -16.3 |

## Fixed strategy per market

| market / data | strategy | trades | avg R | PF | Sharpe | max DD (R) | profitable years | R 2025-26 |
|---|---|---|---|---|---|---|---|---|
| NDX100 Dukascopy 2013-26 | momentum | 1118 | 0.094 | 1.2 | 1.46 | 19.8 | 11/14 | 4.6 |
| NDX100 OANDA 2005-19 | momentum | 1338 | 0.135 | 1.3 | 1.98 | 15.8 | 15/15 | nan |
| SPX500 OANDA 2005-19 | momentum | 1427 | 0.154 | 1.34 | 2.26 | 23.2 | 14/15 | nan |
| JP225 OANDA 2010-19 | momentum (Tokyo) | 730 | 0.116 | 1.25 | 1.68 | 14.8 | 8/10 | nan |
| XAUUSD Dukascopy 2012-26 | swing long+short | 648 | 0.153 | 1.28 | 1.43 | 25.8 | 11/15 | 32.4 |
| XAUUSD OANDA 2006-19 | swing long+short | 680 | 0.156 | 1.29 | 1.55 | 16.3 | 11/14 | nan |

## Prop challenge simulation (one attempt; +10 % target, 5 % daily, 10 % max, EA halt at -8 %)

| markets | start dates | risk per trade | pass <= 60 d | pass <= 120 d | pass eventually | halted | median days |
|---|---|---|---|---|---|---|---|
| 3 indices momentum | from 2010 | 0.5 % | 14% | 44% | 93% | 3% | 129 |
| 3 indices momentum | from 2010 | 0.75 % | 36% | 64% | 86% | 10% | 71 |
| 3 indices momentum | from 2010 | 1.0 % | 50% | 72% | 81% | 14% | 49 |
| 3 indices momentum | from 2010 | Sprint | 58% | 60% | 60% | 35% | 9 |
| 3 indices + gold swing | from 2010 | 0.5 % | 16% | 47% | 92% | 2% | 117 |
| 3 indices + gold swing | from 2010 | 0.75 % | 39% | 67% | 83% | 10% | 65 |
| 3 indices + gold swing | from 2010 | 1.0 % | 56% | 74% | 79% | 14% | 42 |
| 3 indices + gold swing | from 2010 | Sprint | 54% | 55% | 55% | 38% | 9 |
| NDX100 momentum | from 2020 | 0.5 % | 0% | 0% | 73% | 0% | 394 |
| NDX100 momentum | from 2020 | 0.75 % | 2% | 12% | 76% | 0% | 262 |
| NDX100 momentum | from 2020 | 1.0 % | 9% | 22% | 74% | 2% | 161 |
| NDX100 momentum | from 2020 | Sprint | 47% | 58% | 62% | 32% | 18 |
| NDX100 + gold swing | from 2020 | 0.5 % | 1% | 3% | 92% | 0% | 332 |
| NDX100 + gold swing | from 2020 | 0.75 % | 9% | 27% | 90% | 3% | 189 |
| NDX100 + gold swing | from 2020 | 1.0 % | 19% | 46% | 82% | 6% | 111 |
| NDX100 + gold swing | from 2020 | Sprint | 50% | 56% | 58% | 35% | 18 |
| NDX100 momentum | from 2025 | 0.5 % | 0% | 0% | 0% | 0% | - |
| NDX100 momentum | from 2025 | 0.75 % | 0% | 0% | 0% | 0% | - |
| NDX100 momentum | from 2025 | 1.0 % | 0% | 0% | 2% | 1% | 464 |
| NDX100 momentum | from 2025 | Sprint | 25% | 38% | 48% | 38% | 49 |
| NDX100 + gold swing | from 2025 | 0.5 % | 0% | 0% | 65% | 0% | 252 |
| NDX100 + gold swing | from 2025 | 0.75 % | 5% | 18% | 79% | 0% | 165 |
| NDX100 + gold swing | from 2025 | 1.0 % | 19% | 52% | 81% | 3% | 101 |
| NDX100 + gold swing | from 2025 | Sprint | 50% | 55% | 57% | 37% | 26 |

Markets without a robust edge in these tests: EURUSD, GBPUSD, USDJPY (long-only trend = past drift, lost in 2025-26), XAGUSD and BTCUSD (gold swing settings unprofitable), UK100 and FR40 (momentum weak).
