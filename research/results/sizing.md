# Position-sizing policies (one challenge attempt: +10 % target, 5 % daily, 10 % max, EA halt at -8 %)

Cushion = balance minus the -8 % halt level (8 % at the start). Risk per trade = multiplier x cushion,
capped; all policies are also capped by the 4 % daily / 9.5 % total worst-case budget (open stops included).

## 3 indices + gold, 2010-19

| policy | pass <= 120 d | pass eventually | halted | median days |
|---|---|---|---|---|
| fixed 0.5 % | 48 % | 94 % | 2 % | 119 |
| fixed 0.75 % | 69 % | 86 % | 10 % | 65 |
| fixed 1.0 % | 74 % | 79 % | 14 % | 42 |
| cushion x0.10, max 2 % | 66 % | 93 % | 1 % | 61 |
| **cushion x0.15, max 2 %** | 69 % | 86 % | 5 % | 38 |
| cushion x0.15, max 1.5 % | 70 % | 86 % | 5 % | 38 |
| cushion x0.20, max 2 % | 70 % | 81 % | 9 % | 29 |
| step 0.75 % -> 1.2 % after +2 % | 71 % | 84 % | 11 % | 51 |
| half risk in a 3 % drawdown (1 %) | 61 % | 88 % | 6 % | 65 |
| sprint (target-based, max 4 %) | 55 % | 55 % | 39 % | 9 |

## NDX100 + gold, 2020-26

| policy | pass <= 120 d | pass eventually | halted | median days |
|---|---|---|---|---|
| fixed 0.5 % | 3 % | 92 % | 0 % | 332 |
| fixed 0.75 % | 27 % | 90 % | 3 % | 189 |
| fixed 1.0 % | 46 % | 82 % | 6 % | 111 |
| cushion x0.10, max 2 % | 41 % | 96 % | 0 % | 150 |
| **cushion x0.15, max 2 %** | 52 % | 97 % | 0 % | 111 |
| cushion x0.15, max 1.5 % | 52 % | 96 % | 0 % | 112 |
| cushion x0.20, max 2 % | 56 % | 81 % | 2 % | 71 |
| step 0.75 % -> 1.2 % after +2 % | 43 % | 91 % | 3 % | 130 |
| half risk in a 3 % drawdown (1 %) | 38 % | 91 % | 1 % | 154 |
| sprint (target-based, max 4 %) | 56 % | 58 % | 38 % | 18 |

## NDX100 + gold, starts 2025-26

| policy | pass <= 120 d | pass eventually | halted | median days |
|---|---|---|---|---|
| fixed 0.5 % | 0 % | 65 % | 0 % | 252 |
| fixed 0.75 % | 18 % | 79 % | 0 % | 165 |
| fixed 1.0 % | 52 % | 81 % | 3 % | 101 |
| cushion x0.10, max 2 % | 44 % | 82 % | 0 % | 112 |
| **cushion x0.15, max 2 %** | 64 % | 87 % | 0 % | 80 |
| cushion x0.15, max 1.5 % | 58 % | 82 % | 0 % | 85 |
| cushion x0.20, max 2 % | 65 % | 86 % | 0 % | 67 |
| step 0.75 % -> 1.2 % after +2 % | 46 % | 84 % | 0 % | 114 |
| half risk in a 3 % drawdown (1 %) | 40 % | 80 % | 0 % | 120 |
| sprint (target-based, max 4 %) | 55 % | 57 % | 43 % | 26 |

Rejected: capping total open risk (lowers pass rates, halts unchanged); giving gold more risk than an
index (x1.5-2 raises halts to 8-14 % in 2010-19).
