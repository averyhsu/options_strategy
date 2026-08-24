# P5 intraday defense grid — SYNTHETIC world

**SYNTHETIC DATA** (`theta_decade_world_v2`) — Pass-1 dress rehearsal: near-miss P4
configs (selection rule in eval/p5_grid.py) run through the REAL Track-B
engine with resting EV-gated entries and intraday touch monitoring.
Fill-model bounds reported side-by-side per PLAN §7.2 (CONSERVATIVE = lower
bound; MID = central; OPTIMISTIC never headlines).

## Config 0

```
coverage_q_call=0.8984803732950241, coverage_q_put=0.8062168459873646, credit_threshold_frac=0.21067306399345398, defense=none, ema_len=34, exit_mode=exit_7dte, front_dte=14, hysteresis=0.0, long_call_offset_days=39, long_put_offset_days=9, long_strike_offset=15.0, min_credit_frac=0.12029223013669253, regime_action=retracement_only, require_credit=False, risk_definition=width, risk_fraction=0.1, short_call_delta=0.19379040352068844, short_put_delta=0.2622314190026373, strike_family=delta, threshold_reference=scenario_r, wing_family=near
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 94,964 | 94,964 | 28.5% | 28.5% | -6.1% | 0 | 96/96 |
| close_tested_side/immediate | 113,960 | 113,960 | 23.0% | 23.0% | -7.9% | 34 | 129/129 |
| buy_back_short/immediate | 64,790 | 64,790 | 35.3% | 35.3% | -4.9% | 31 | 111/111 |
| roll_out/immediate | 134,817 | 134,817 | 22.1% | 22.1% | -8.1% | 35 | 142/142 |
| roll_out_away/immediate | 101,117 | 101,117 | 30.7% | 30.7% | -5.9% | 33 | 128/128 |
| convert_vertical/immediate | 107,988 | 107,988 | 21.8% | 21.8% | -7.0% | 34 | 131/131 |
| close_all/immediate | 95,454 | 95,454 | 28.7% | 28.7% | -12.2% | 33 | 106/106 |
| delta_hedge/immediate | -1,280,307 | -1,280,307 | 1365.3% | 1365.3% | -1209.9% | 25 | 64/64 |
| close_tested_side/t-1 | 81,156 | 81,156 | 43.6% | 43.6% | -9.2% | 21 | 110/110 |
| buy_back_short/t-1 | 97,551 | 97,551 | 31.0% | 31.0% | -6.3% | 21 | 118/118 |

## Config 1

```
coverage_q_call=0.8980977600906045, coverage_q_put=0.8915633715689183, credit_threshold_frac=0.36076398454606534, defense=none, ema_len=13, exit_mode=exit_7dte, front_dte=14, hysteresis=0.0, long_call_offset_days=14, long_put_offset_days=22, long_strike_offset=95.0, min_credit_frac=0.08970680218189955, regime_action=retracement_only, require_credit=False, risk_definition=scenario, risk_fraction=0.2, short_call_delta=0.09846841376274824, short_put_delta=0.3585393062327057, strike_family=delta, threshold_reference=max_gain, wing_family=wide
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 86,782 | 86,782 | 21.8% | 21.8% | -3.3% | 0 | 112/112 |
| close_tested_side/immediate | 57,210 | 57,210 | 44.5% | 44.5% | -21.9% | 42 | 130/130 |
| buy_back_short/immediate | 71,015 | 71,015 | 36.4% | 36.4% | -10.7% | 52 | 163/163 |
| roll_out/immediate | 166,663 | 166,663 | 36.5% | 36.5% | -11.5% | 52 | 184/184 |
| roll_out_away/immediate | 108,395 | 108,395 | 20.5% | 20.5% | -4.6% | 52 | 170/170 |
| convert_vertical/immediate | 162,461 | 162,461 | 25.7% | 25.7% | -10.0% | 52 | 174/174 |
| close_all/immediate | 71,359 | 71,359 | 44.4% | 44.4% | -21.2% | 51 | 124/124 |
| delta_hedge/immediate | -1,379,696 | -1,379,696 | 1373.2% | 1373.2% | -612.0% | 12 | 22/22 |
| close_tested_side/t-1 | 81,509 | 81,509 | 62.3% | 62.3% | -25.5% | 30 | 144/144 |
| buy_back_short/t-1 | 80,230 | 80,230 | 27.7% | 27.7% | -6.7% | 30 | 142/142 |

## Config 2

```
coverage_q_call=0.829981538746506, coverage_q_put=0.8934275628533215, credit_threshold_frac=0.347340127825737, defense=none, ema_len=13, exit_mode=exit_7dte, front_dte=7, hysteresis=0.5, long_call_offset_days=22, long_put_offset_days=12, long_strike_offset=95.0, min_credit_frac=0.07903142552822828, regime_action=bull_only, require_credit=False, risk_definition=scenario, risk_fraction=0.1, short_call_delta=0.14805543231777846, short_put_delta=0.463196429843083, strike_family=percentile, threshold_reference=width, wing_family=wide
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 84,511 | 84,511 | 20.7% | 20.7% | -8.1% | 0 | 34/34 |
| close_tested_side/immediate | 91,271 | 91,271 | 13.8% | 13.8% | -2.8% | 49 | 112/112 |
| buy_back_short/immediate | 74,342 | 74,342 | 35.5% | 35.5% | -7.6% | 44 | 99/99 |
| roll_out/immediate | 82,255 | 82,255 | 23.7% | 23.7% | -5.8% | 28 | 62/62 |
| roll_out_away/immediate | 76,270 | 76,270 | 28.2% | 28.2% | -5.4% | 41 | 90/90 |
| convert_vertical/immediate | 79,205 | 79,205 | 22.1% | 22.1% | -3.8% | 29 | 60/60 |
| close_all/immediate | 96,373 | 96,373 | 12.3% | 12.3% | -2.8% | 59 | 138/138 |
| delta_hedge/immediate | -7,540,169 | -7,540,169 | 1329.8% | 1329.8% | -5524.2% | 89 | 141/141 |
| close_tested_side/t-1 | 85,436 | 85,436 | 16.3% | 16.3% | -4.0% | 18 | 59/59 |
| buy_back_short/t-1 | 80,675 | 80,675 | 29.3% | 29.3% | -8.3% | 19 | 60/60 |

## Config 3

```
coverage_q_call=0.8078385464381427, coverage_q_put=0.9158811488188804, credit_threshold_frac=0.4703847698867321, defense=none, ema_len=13, exit_mode=exit_7dte, front_dte=14, hysteresis=0.5, long_call_offset_days=37, long_put_offset_days=49, long_strike_offset=100.0, min_credit_frac=0.16968204732984304, regime_action=retracement_only, require_credit=False, risk_definition=margin, risk_fraction=0.15, short_call_delta=0.07566488669253886, short_put_delta=0.3521635202225298, strike_family=delta, threshold_reference=width, wing_family=wide
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 88,336 | 88,336 | 24.4% | 24.4% | -6.1% | 0 | 217/217 |
| close_tested_side/immediate | 81,807 | 81,807 | 34.1% | 34.1% | -13.8% | 96 | 313/313 |
| buy_back_short/immediate | 60,682 | 60,682 | 39.5% | 39.5% | -3.1% | 71 | 221/221 |
| roll_out/immediate | 160,563 | 160,563 | 19.8% | 19.8% | -7.2% | 96 | 316/316 |
| roll_out_away/immediate | 64,435 | 64,435 | 38.4% | 38.4% | -8.3% | 89 | 285/285 |
| convert_vertical/immediate | 205,869 | 205,869 | 26.3% | 26.3% | -6.1% | 96 | 322/322 |
| close_all/immediate | 104,037 | 104,037 | 26.8% | 26.8% | -11.3% | 96 | 246/246 |
| delta_hedge/immediate | -909,985 | -909,985 | 991.5% | 991.5% | -2361.9% | 22 | 47/47 |
| close_tested_side/t-1 | 91,840 | 91,840 | 68.2% | 68.2% | -35.3% | 51 | 285/285 |
| buy_back_short/t-1 | 63,104 | 63,104 | 46.7% | 46.7% | -13.9% | 40 | 210/210 |

## Config 4

```
coverage_q_call=0.8739201912656427, coverage_q_put=0.8627708066254854, credit_threshold_frac=0.5120360035449267, defense=none, ema_len=34, exit_mode=exit_7dte, front_dte=14, hysteresis=0.0, long_call_offset_days=39, long_put_offset_days=11, long_strike_offset=15.0, min_credit_frac=0.06144555099308491, regime_action=retracement_only, require_credit=False, risk_definition=width, risk_fraction=0.15, short_call_delta=0.2512418173253536, short_put_delta=0.3262736154720187, strike_family=delta, threshold_reference=scenario_r, wing_family=near
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 83,265 | 83,265 | 17.9% | 17.9% | -7.3% | 0 | 103/103 |
| close_tested_side/immediate | 78,636 | 78,636 | 40.9% | 40.9% | -10.5% | 54 | 160/160 |
| buy_back_short/immediate | 39,042 | 39,042 | 61.0% | 61.0% | -15.3% | 44 | 124/124 |
| roll_out/immediate | 186,919 | 186,919 | 33.5% | 33.5% | -17.6% | 55 | 228/228 |
| roll_out_away/immediate | 61,191 | 61,191 | 40.7% | 40.7% | -9.1% | 53 | 149/149 |
| convert_vertical/immediate | 96,449 | 96,449 | 45.8% | 45.8% | -14.5% | 55 | 156/156 |
| close_all/immediate | 47,099 | 47,099 | 61.7% | 61.7% | -27.6% | 45 | 102/102 |
| delta_hedge/immediate | -1,773,273 | -1,773,273 | 1806.5% | 1806.5% | -588.2% | 37 | 66/66 |
| close_tested_side/t-1 | 59,366 | 59,366 | 56.7% | 56.7% | -16.8% | 26 | 123/123 |
| buy_back_short/t-1 | 76,831 | 76,831 | 28.1% | 28.1% | -8.5% | 28 | 131/131 |

## Config 5

```
coverage_q_call=0.8350191595032812, coverage_q_put=0.9160174435935915, credit_threshold_frac=0.31626100465655327, defense=close_side_eod, ema_len=34, exit_mode=exit_7dte, front_dte=14, hysteresis=0.5, long_call_offset_days=16, long_put_offset_days=19, long_strike_offset=70.0, min_credit_frac=0.004781109280884266, regime_action=retracement_only, require_credit=False, risk_definition=margin, risk_fraction=0.2, short_call_delta=0.05783245810307563, short_put_delta=0.26422579479403796, strike_family=delta, threshold_reference=scenario_r, wing_family=wide
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 92,290 | 92,290 | 15.5% | 15.5% | -3.7% | 0 | 179/179 |
| close_tested_side/immediate | 262,193 | 262,193 | 22.2% | 22.2% | -14.6% | 45 | 247/247 |
| buy_back_short/immediate | 40,719 | 40,719 | 64.2% | 64.2% | -12.0% | 39 | 193/193 |
| roll_out/immediate | 190,445 | 190,445 | 50.8% | 50.8% | -16.7% | 45 | 290/290 |
| roll_out_away/immediate | 85,892 | 85,892 | 31.8% | 31.8% | -9.7% | 45 | 225/225 |
| convert_vertical/immediate | 101,729 | 101,729 | 59.6% | 59.6% | -28.2% | 45 | 235/235 |
| close_all/immediate | 343,044 | 343,044 | 21.9% | 21.9% | -14.4% | 45 | 233/233 |
| delta_hedge/immediate | -1,551,301 | -1,551,301 | 1608.7% | 1608.7% | -11293.2% | 17 | 68/68 |
| close_tested_side/t-1 | 77,462 | 77,462 | 77.6% | 77.6% | -39.0% | 22 | 219/219 |
| buy_back_short/t-1 | 108,564 | 108,564 | 23.9% | 23.9% | -8.1% | 22 | 206/206 |

## Config 6

```
coverage_q_call=0.9319134762510658, coverage_q_put=0.9209909073077143, credit_threshold_frac=0.5876265294849873, defense=none, ema_len=34, exit_mode=exit_7dte, front_dte=14, hysteresis=0.0, long_call_offset_days=21, long_put_offset_days=15, long_strike_offset=45.0, min_credit_frac=0.05985192712396384, regime_action=retracement_only, require_credit=False, risk_definition=margin, risk_fraction=0.2, short_call_delta=0.22834890186786655, short_put_delta=0.4522453635465354, strike_family=delta, threshold_reference=width, wing_family=near
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 33,201 | 33,201 | 107.8% | 107.8% | -713.5% | 0 | 124/124 |
| close_tested_side/immediate | 34,917 | 34,917 | 87.7% | 87.7% | -38.1% | 58 | 158/158 |
| buy_back_short/immediate | 20,734 | 20,734 | 80.0% | 80.0% | -10.7% | 52 | 132/132 |
| roll_out/immediate | 67,891 | 67,891 | 105.4% | 105.4% | -463.2% | 58 | 300/300 |
| roll_out_away/immediate | 35,759 | 35,759 | 89.8% | 89.8% | -42.2% | 58 | 182/182 |
| convert_vertical/immediate | 50,602 | 50,602 | 108.8% | 108.8% | -514.3% | 58 | 184/184 |
| close_all/immediate | 47,707 | 47,707 | 96.6% | 96.6% | -61.9% | 58 | 137/137 |
| delta_hedge/immediate | 3,644,872 | 3,644,872 | 144.7% | 144.7% | -980.7% | 58 | 495/495 |
| close_tested_side/t-1 | 22,447 | 22,447 | 94.1% | 94.1% | -49.1% | 30 | 159/159 |
| buy_back_short/t-1 | 54,850 | 54,850 | 107.1% | 107.1% | -291.5% | 31 | 160/160 |

## Config 7

```
coverage_q_call=0.8539094330277295, coverage_q_put=0.8827499108854682, credit_threshold_frac=0.5879654299467802, defense=none, ema_len=34, exit_mode=exit_7dte, front_dte=14, hysteresis=0.0, long_call_offset_days=18, long_put_offset_days=40, long_strike_offset=10.0, min_credit_frac=0.1300732459872961, regime_action=retracement_only, require_credit=False, risk_definition=margin, risk_fraction=0.1, short_call_delta=0.1217958001419902, short_put_delta=0.39214201280847194, strike_family=delta, threshold_reference=width, wing_family=near
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | -301 | -301 | 100.7% | 100.7% | -395.6% | 0 | 163/163 |
| close_tested_side/immediate | -75,611 | -75,611 | 175.6% | 175.6% | -4001.3% | 42 | 134/134 |
| buy_back_short/immediate | 11,933 | 11,933 | 91.2% | 91.2% | -19.4% | 36 | 110/110 |
| roll_out/immediate | -131,230 | -131,230 | 111.5% | 111.5% | -417.8% | 48 | 1466/1466 |
| roll_out_away/immediate | -16,890 | -16,890 | 115.9% | 115.9% | -120.3% | 48 | 260/260 |
| convert_vertical/immediate | -1,008,888 | -1,008,888 | 244.2% | 244.2% | -7783.7% | 43 | 602/602 |
| close_all/immediate | -922,336 | -922,336 | 451.9% | 451.9% | -2132.6% | 43 | 259/259 |
| delta_hedge/immediate | -2,095,592 | -2,095,592 | 1914.1% | 1914.1% | -891.1% | 23 | 48/48 |
| close_tested_side/t-1 | -2,025,821 | -2,025,821 | 338.8% | 338.8% | -7407.9% | 20 | 618/618 |
| buy_back_short/t-1 | 19,390 | 19,390 | 91.1% | 91.1% | -47.6% | 22 | 118/118 |
