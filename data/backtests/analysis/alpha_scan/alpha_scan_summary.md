DEEP6 signal alpha scan
Primary ranking window: 5 bars

Top 15 signals by 5-bar expectancy
signal_id | category | N | WR | avg_5b | sharpe_5b
---|---:|---:|---:|---:|---:
DELT_07 | delta | 3 | 33.3% | 453.33 | 0.56
ABS_04 | absorption | 41 | 53.7% | 199.78 | 0.37
VOLP_06 | volume_profile | 32 | 56.2% | 104.16 | 0.17
AUCT_03 | auction | 46 | 54.3% | 8.43 | 0.13
TRAP_04 | trapped | 9964 | 49.0% | 4.26 | 0.02
EXH_03 | exhaustion | 62714 | 50.4% | 1.13 | 0.01
DELT_04 | delta | 20669 | 50.2% | 0.80 | 0.01
EXH_01 | exhaustion | 52439 | 50.4% | 0.62 | 0.00
EXH_04 | exhaustion | 466 | 48.3% | 0.56 | 0.01
EXH_05 | exhaustion | 27134 | 49.6% | 0.56 | 0.00
DELT_01 | delta | 87419 | 49.7% | 0.22 | 0.00
IMB_04 | imbalance | 61498 | 49.7% | 0.18 | 0.00
IMB_03 | imbalance | 118235 | 49.5% | -0.05 | -0.00
IMB_05 | imbalance | 60517 | 49.8% | -0.07 | -0.00
EXH_02 | exhaustion | 9735 | 49.4% | -0.17 | -0.00

Category leaderboard by 5-bar expectancy
category | signals | N | WR | avg_5b | sharpe_5b
---|---:|---:|---:|---:|---:
exhaustion | 5 | 152488 | 50.2% | 0.77 | 0.01
delta | 5 | 138864 | 49.7% | -0.10 | -0.00
trapped | 3 | 184706 | 49.1% | -0.39 | -0.00
auction | 5 | 418455 | 49.5% | -0.50 | -0.00
imbalance | 9 | 737639 | 49.4% | -0.50 | -0.00
other | 2 | 119489 | 49.1% | -0.82 | -0.01
volume_profile | 2 | 1588 | 47.1% | -1.27 | -0.00
poc | 1 | 1884 | 49.4% | -1.56 | -0.02
absorption | 3 | 901 | 46.3% | -3.24 | -0.01

Overall score-tier edge by 5-bar expectancy
score_tier | N | WR | avg_5b | sharpe_5b
---|---:|---:|---:|---:
TYPE_B | 43192 | 48.6% | 0.15 | 0.00
QUIET | 1047323 | 49.2% | -0.07 | -0.00
TYPE_C | 648748 | 49.1% | -0.71 | -0.00
TYPE_A | 16751 | 48.4% | -7.40 | -0.02

Top 10 deep-dive signals (N >= 30 on 5b if available)
signal_id | category | N | WR | avg_1b | avg_5b | avg_10b | avg_15b | avg_30b | TYPE_A avg_5b | TYPE_B avg_5b | TYPE_C avg_5b | best ET hours
---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---
ABS_04 | absorption | 41 | 53.7% | 2.29 | 199.78 | 202.90 | 172.24 | 127.41 | -199.71 | 347.38 | 277.47 | 15, 13, 14
VOLP_06 | volume_profile | 32 | 56.2% | 108.72 | 104.16 | 152.53 | 192.94 | 101.88 | 31.00 | 154.21 | nan | 15
AUCT_03 | auction | 46 | 54.3% | -0.11 | 8.43 | 3.85 | 6.37 | 35.30 | nan | nan | 16.00 | 13, 11, 14
TRAP_04 | trapped | 9964 | 49.0% | -0.10 | 4.26 | 1.70 | 3.18 | 3.08 | -6.91 | 44.85 | 6.32 | 15, 09, 10
EXH_03 | exhaustion | 62714 | 50.4% | 0.34 | 1.13 | 0.16 | 1.22 | 3.30 | 6.51 | 7.53 | 0.35 | 09, 11, 10
DELT_04 | delta | 20669 | 50.2% | 0.31 | 0.80 | -0.52 | 0.78 | 3.31 | 28.18 | 0.26 | 0.07 | 15, 13, 11
EXH_01 | exhaustion | 52439 | 50.4% | 0.09 | 0.62 | -1.08 | -0.70 | -1.64 | -8.70 | 3.40 | -0.17 | 11, 09, 14
EXH_04 | exhaustion | 466 | 48.3% | 1.66 | 0.56 | 6.27 | -7.32 | 13.67 | 48.50 | 37.14 | 1.83 | 10, 09, 14
EXH_05 | exhaustion | 27134 | 49.6% | 0.13 | 0.56 | -0.03 | 1.43 | 2.38 | -5.92 | 1.21 | -1.67 | 11, 12, 14
DELT_01 | delta | 87419 | 49.7% | -0.43 | 0.22 | 0.19 | 0.44 | -0.48 | -5.72 | 0.90 | 0.45 | 15, 12, 13

Top 10 absorption interaction (5b)
signal_id | interaction | N | WR | avg_5b | sharpe_5b
---|---|---:|---:|---:|---:
ABS_04 | adjacent_bar | 7 | 57.1% | 207.71 | 0.38
ABS_04 | same_bar | 41 | 53.7% | 199.78 | 0.37
ABS_04 | same_or_adjacent | 41 | 53.7% | 199.78 | 0.37
AUCT_03 | adjacent_bar | 1 | 0.0% | -41.00 | nan
AUCT_03 | no_absorption_nearby | 41 | 58.5% | 5.71 | 0.10
AUCT_03 | same_bar | 4 | 25.0% | 48.75 | 0.35
AUCT_03 | same_or_adjacent | 5 | 20.0% | 30.80 | 0.24
DELT_01 | adjacent_bar | 1215 | 46.6% | 9.16 | 0.03
DELT_01 | no_absorption_nearby | 85479 | 49.7% | -0.05 | -0.00
DELT_01 | same_bar | 768 | 53.9% | 18.91 | 0.07
DELT_01 | same_or_adjacent | 1940 | 49.3% | 12.28 | 0.05
DELT_04 | adjacent_bar | 445 | 48.3% | -0.71 | -0.00
DELT_04 | no_absorption_nearby | 20013 | 50.2% | 0.83 | 0.01
DELT_04 | same_bar | 228 | 51.8% | 6.04 | 0.04
DELT_04 | same_or_adjacent | 656 | 49.4% | 0.04 | 0.00
EXH_01 | adjacent_bar | 690 | 49.7% | -2.83 | -0.01
EXH_01 | no_absorption_nearby | 51558 | 50.4% | 0.50 | 0.00
EXH_01 | same_bar | 220 | 52.3% | 39.99 | 0.15
EXH_01 | same_or_adjacent | 881 | 50.2% | 7.43 | 0.03
EXH_03 | adjacent_bar | 859 | 49.8% | -4.01 | -0.02
EXH_03 | no_absorption_nearby | 61650 | 50.4% | 0.98 | 0.01
EXH_03 | same_bar | 238 | 56.3% | 80.19 | 0.24
EXH_03 | same_or_adjacent | 1064 | 50.8% | 10.26 | 0.04
EXH_04 | adjacent_bar | 34 | 47.1% | 13.09 | 0.08
EXH_04 | no_absorption_nearby | 425 | 48.0% | -0.31 | -0.00
EXH_04 | same_bar | 13 | 76.9% | 54.31 | 0.30
EXH_04 | same_or_adjacent | 41 | 51.2% | 9.54 | 0.06
EXH_05 | adjacent_bar | 355 | 49.6% | -32.65 | -0.12
EXH_05 | no_absorption_nearby | 26650 | 49.6% | 0.89 | 0.01
EXH_05 | same_bar | 148 | 46.6% | 30.37 | 0.10
EXH_05 | same_or_adjacent | 484 | 48.6% | -17.51 | -0.06
TRAP_04 | adjacent_bar | 569 | 45.7% | -4.72 | -0.01
TRAP_04 | no_absorption_nearby | 8581 | 48.9% | 3.91 | 0.02
TRAP_04 | same_bar | 882 | 53.5% | 15.34 | 0.05
TRAP_04 | same_or_adjacent | 1383 | 50.3% | 6.40 | 0.02
VOLP_06 | adjacent_bar | 4 | 50.0% | -25.50 | -0.14
VOLP_06 | no_absorption_nearby | 26 | 57.7% | 154.85 | 0.24
VOLP_06 | same_bar | 3 | 66.7% | -146.67 | -0.29
VOLP_06 | same_or_adjacent | 6 | 50.0% | -115.50 | -0.35

Signal-of-signals scenarios
scenario | bars | avg_1b | avg_5b | avg_10b | avg_15b | avg_30b
---|---:|---:|---:|---:|---:|---:
type_a_any | 985 | -10.67 | -23.59 | -26.78 | -18.07 | -14.54
type_a_2plus_categories | 985 | -10.67 | -23.59 | -26.78 | -18.07 | -14.54
type_a_plus_absorption_any | 57 | 0.75 | -29.63 | -35.25 | 2.51 | 39.53
type_a_plus_absorption_type_a | 57 | 0.75 | -29.63 | -35.25 | 2.51 | 39.53
