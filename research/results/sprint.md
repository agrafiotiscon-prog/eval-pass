# Sprint mode results

Sizing: risk = (target - profit) / 2.5 per trade, capped at 4 % of the initial balance and by the room left before a 4 % worst-case daily loss / 9.5 % worst-case total loss (open stops included). The attempt is abandoned (EA halts) at -8 %; 'free restarts' starts a new challenge the next day. Every calendar day is a start date. With a 4-trading-day minimum and the helper enabled the pass rates are unchanged.

|                                       |   NAS100 + US500 (2005-19) |   NAS100 + US500 + US2000 (2005-19) |   NAS100 + US500 + US2000 + JP225 (2010-19) |   NAS100 only (Dukascopy 2020-26) |
|:--------------------------------------|---------------------------:|------------------------------------:|--------------------------------------------:|----------------------------------:|
| pass <= 7 days %                      |                      23    |                               24.7  |                                       27    |                             20.1  |
| pass <= 14 days %                     |                      31.2  |                               35.2  |                                       37.1  |                             27.3  |
| pass <= 30 days %                     |                      44    |                               48.5  |                                       51.2  |                             37.4  |
| halted at -8 % within 30 days %       |                      33.4  |                               34.1  |                                       35.4  |                             29    |
| median days to funded (free restarts) |                      20    |                               17    |                                       15    |                             38    |
| 75th pct days to funded               |                      43    |                               38    |                                       29    |                             85    |
| average attempts                      |                       1.57 |                                1.62 |                                        1.63 |                              1.51 |

## Standard sizing on more markets (reference)

| markets | risk/trade | pass % | fail % | open % | median days |
|---|---|---|---|---|---|
| NAS100 + US500 + US2000 (2005-19) | 0.50% | 82.6 | 4.0 | 13.3 | 117.0 |
| NAS100 + US500 + US2000 (2005-19) | 0.75% | 84.8 | 13.0 | 2.2 | 70.0 |
| NAS100 + US500 + US2000 + JP225 (2010-19) | 0.50% | 87.6 | 5.1 | 7.3 | 99.0 |
| NAS100 + US500 + US2000 + JP225 (2010-19) | 0.75% | 86.1 | 11.5 | 2.4 | 52.0 |

US2000 (2005-19): 1314 trades, avg R 0.106, profitable years 12/15

JP225 (2005-19 data, trades from 2010): 730 trades, avg R 0.116, profitable years 8/10
