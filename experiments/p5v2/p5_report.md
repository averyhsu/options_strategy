# P5 intraday defense grid — SYNTHETIC world

**SYNTHETIC DATA** (`synthetic-b555e1ab2c37`) — Pass-1 dress rehearsal: near-miss P4
configs (selection rule in eval/p5_grid.py) run through the REAL Track-B
engine with resting EV-gated entries and intraday touch monitoring.
Fill-model bounds reported side-by-side per PLAN §7.2 (CONSERVATIVE = lower
bound; MID = central; OPTIMISTIC never headlines).

## Config 0

```
coverage_q_call=0.9207044314593077, coverage_q_put=0.9000847776886076, credit_threshold_frac=0.38238205127418046, defense=none, ema_len=34, hysteresis=0.5, long_call_offset_days=16, long_put_offset_days=16, long_strike_offset=80.0, min_credit_frac=0.017089285142719745, regime_action=retracement_only, require_credit=True, risk_definition=width, risk_fraction=0.15, short_call_delta=0.4431092688813806, short_put_delta=0.1941392918583006, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 95,342 | 97,762 | 7.0% | 6.9% | -5.0% | 0 | 3/5 |
| close_tested_side/immediate | 98,551 | 99,820 | 1.5% | 1.7% | -0.6% | 5 | 4/9 |
| buy_back_short/immediate | 97,494 | 99,571 | 2.9% | 2.6% | -1.5% | 5 | 4/10 |
| roll_out/immediate | 95,375 | 96,600 | 8.0% | 9.1% | -4.6% | 5 | 5/10 |
| roll_out_away/immediate | 97,329 | 98,036 | 3.4% | 4.6% | -1.5% | 5 | 4/9 |
| convert_vertical/immediate | 98,891 | 99,546 | 1.5% | 4.2% | -1.1% | 5 | 4/9 |
| close_all/immediate | 99,029 | 100,764 | 1.0% | 0.5% | -0.4% | 5 | 4/9 |
| delta_hedge/immediate | 95,833 | -31,145 | 14.7% | 177.5% | -1116.1% | 2 | 2/2 |
| close_tested_side/t-1 | 101,491 | 102,685 | 1.0% | 1.1% | -0.5% | 5 | 5/9 |
| buy_back_short/t-1 | 100,731 | 103,183 | 2.4% | 2.3% | -1.5% | 5 | 5/10 |

## Config 1

```
coverage_q_call=0.8821933664847166, coverage_q_put=0.8681912696920335, credit_threshold_frac=0.33244506195187573, defense=none, ema_len=21, hysteresis=0.5, long_call_offset_days=10, long_put_offset_days=11, long_strike_offset=90.0, min_credit_frac=0.041139920242130756, regime_action=retracement_only, require_credit=True, risk_definition=margin, risk_fraction=0.15, short_call_delta=0.3841527184005827, short_put_delta=0.25219978839159013, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 79,380 | 58,619 | 23.7% | 41.4% | -8.8% | 0 | 7/20 |
| close_tested_side/immediate | 98,824 | 91,423 | 3.1% | 9.3% | -2.9% | 27 | 14/41 |
| buy_back_short/immediate | 95,433 | 85,331 | 13.1% | 16.5% | -6.3% | 27 | 15/49 |
| roll_out/immediate | 89,775 | 58,496 | 14.8% | 41.5% | -9.4% | 23 | 15/40 |
| roll_out_away/immediate | 90,919 | 76,822 | 10.8% | 25.5% | -4.2% | 27 | 15/47 |
| convert_vertical/immediate | 100,632 | 92,075 | 4.0% | 12.0% | -3.0% | 27 | 15/47 |
| close_all/immediate | 120,599 | 108,036 | 1.9% | 13.0% | -2.9% | 27 | 14/36 |
| delta_hedge/immediate | 74,640 | -62,681 | 34.8% | 191.0% | -306.9% | 9 | 7/8 |
| close_tested_side/t-1 | 91,852 | 80,655 | 10.3% | 21.5% | -7.9% | 21 | 12/38 |
| buy_back_short/t-1 | 80,948 | 61,952 | 21.8% | 40.2% | -8.6% | 21 | 13/43 |

## Config 2

```
coverage_q_call=0.8372849246952683, coverage_q_put=0.9304218492470682, credit_threshold_frac=0.5622144348919391, defense=close_side_eod, ema_len=21, hysteresis=0.5, long_call_offset_days=20, long_put_offset_days=8, long_strike_offset=65.0, min_credit_frac=0.02521800771355629, regime_action=trade_all, require_credit=True, risk_definition=scenario, risk_fraction=0.2, short_call_delta=0.4137177654076368, short_put_delta=0.43195129320956765, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 77,936 | 71,938 | 23.3% | 31.5% | -13.4% | 0 | 2/13 |
| close_tested_side/immediate | 100,761 | 109,355 | 2.7% | 2.7% | -1.1% | 17 | 6/29 |
| buy_back_short/immediate | 97,201 | 101,693 | 16.8% | 18.1% | -10.1% | 17 | 6/27 |
| roll_out/immediate | 77,551 | 63,088 | 23.2% | 38.9% | -10.6% | 17 | 6/27 |
| roll_out_away/immediate | 87,736 | 86,782 | 18.1% | 19.0% | -11.7% | 17 | 6/20 |
| convert_vertical/immediate | 94,676 | 112,569 | 7.8% | 3.6% | -1.3% | 17 | 4/28 |
| close_all/immediate | 98,672 | 101,074 | 1.3% | 1.6% | -1.2% | 17 | 6/29 |
| delta_hedge/immediate | 84,540 | -191,702 | 32.6% | 236.4% | -1168.8% | 6 | 2/4 |
| close_tested_side/t-1 | 92,231 | 103,600 | 9.8% | 9.4% | -7.4% | 13 | 4/24 |
| buy_back_short/t-1 | 81,364 | 89,339 | 19.9% | 20.4% | -11.8% | 13 | 4/26 |

## Config 3

```
coverage_q_call=0.9015764453448356, coverage_q_put=0.9244509784504772, credit_threshold_frac=0.2740504775196314, defense=close_side_eod, ema_len=13, hysteresis=0.0, long_call_offset_days=22, long_put_offset_days=10, long_strike_offset=100.0, min_credit_frac=0.06292237248271704, regime_action=trade_all, require_credit=True, risk_definition=margin, risk_fraction=0.15, short_call_delta=0.4097826802171767, short_put_delta=0.3583817499224097, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 57,599 | 61,959 | 42.4% | 39.6% | -4.2% | 0 | 10/34 |
| close_tested_side/immediate | 91,640 | 64,627 | 9.4% | 35.4% | -9.0% | 62 | 35/97 |
| buy_back_short/immediate | 85,625 | 64,490 | 20.7% | 38.9% | -10.2% | 54 | 35/91 |
| roll_out/immediate | 63,163 | 65,408 | 37.6% | 35.4% | -4.5% | 38 | 28/62 |
| roll_out_away/immediate | 67,978 | 60,371 | 33.8% | 42.3% | -11.7% | 44 | 35/69 |
| convert_vertical/immediate | 63,730 | 47,335 | 38.4% | 53.7% | -10.7% | 59 | 25/95 |
| close_all/immediate | 125,825 | 103,289 | 9.1% | 31.6% | -8.6% | 70 | 35/108 |
| delta_hedge/immediate | 61,156 | 45,756 | 50.5% | 65.5% | -19.6% | 27 | 8/21 |
| close_tested_side/t-1 | 79,198 | 66,276 | 26.7% | 34.0% | -9.5% | 37 | 26/66 |
| buy_back_short/t-1 | 71,870 | 62,592 | 30.0% | 40.5% | -11.4% | 35 | 27/68 |

## Config 4

```
coverage_q_call=0.8252024992834777, coverage_q_put=0.8530788709409536, credit_threshold_frac=0.31638144813478, defense=close_side_eod, ema_len=21, hysteresis=0.25, long_call_offset_days=11, long_put_offset_days=22, long_strike_offset=90.0, min_credit_frac=0.06449441015720368, regime_action=trade_all, require_credit=True, risk_definition=scenario, risk_fraction=0.15, short_call_delta=0.45470000682398676, short_put_delta=0.38621904151514175, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 51,598 | 51,371 | 49.7% | 50.5% | -9.4% | 0 | 8/15 |
| close_tested_side/immediate | 98,721 | 88,325 | 7.4% | 12.8% | -7.1% | 25 | 23/43 |
| buy_back_short/immediate | 91,127 | 72,292 | 19.8% | 32.0% | -10.9% | 25 | 23/44 |
| roll_out/immediate | 60,958 | 45,372 | 42.7% | 56.2% | -15.6% | 22 | 23/38 |
| roll_out_away/immediate | 68,920 | 50,834 | 36.8% | 50.9% | -14.3% | 22 | 23/37 |
| convert_vertical/immediate | 99,479 | 83,886 | 8.4% | 22.7% | -7.8% | 25 | 22/42 |
| close_all/immediate | 138,866 | 122,370 | 1.7% | 20.6% | -3.6% | 25 | 27/42 |
| delta_hedge/immediate | 42,298 | 42,611 | 69.0% | 86.2% | -38.2% | 11 | 8/9 |
| close_tested_side/t-1 | 75,787 | 63,860 | 29.5% | 42.0% | -8.3% | 20 | 18/36 |
| buy_back_short/t-1 | 69,735 | 46,385 | 35.2% | 54.7% | -10.1% | 15 | 18/27 |

## Config 5

```
coverage_q_call=0.885983063094318, coverage_q_put=0.8557880568318069, credit_threshold_frac=0.33864568099379544, defense=none, ema_len=21, hysteresis=0.5, long_call_offset_days=34, long_put_offset_days=9, long_strike_offset=95.0, min_credit_frac=0.015809913352131843, regime_action=bull_only, require_credit=True, risk_definition=margin, risk_fraction=0.15, short_call_delta=0.10569476429373026, short_put_delta=0.47213392620906236, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 76,045 | 55,551 | 29.3% | 45.3% | -10.5% | 0 | 6/18 |
| close_tested_side/immediate | 97,515 | 86,706 | 5.0% | 15.1% | -8.6% | 19 | 13/37 |
| buy_back_short/immediate | 93,496 | 81,580 | 16.7% | 20.7% | -8.7% | 19 | 13/38 |
| roll_out/immediate | 85,091 | 60,462 | 21.1% | 40.6% | -10.5% | 16 | 13/32 |
| roll_out_away/immediate | 89,424 | 72,143 | 16.2% | 30.7% | -9.1% | 19 | 13/34 |
| convert_vertical/immediate | 98,380 | 89,586 | 3.8% | 14.5% | -8.5% | 19 | 13/37 |
| close_all/immediate | 98,167 | 88,083 | 1.8% | 13.0% | -8.5% | 19 | 12/36 |
| delta_hedge/immediate | 83,098 | 67,997 | 32.8% | 92.9% | -37.9% | 16 | 6/18 |
| close_tested_side/t-1 | 75,475 | 62,856 | 30.3% | 38.1% | -9.5% | 9 | 10/23 |
| buy_back_short/t-1 | 74,736 | 59,866 | 31.1% | 41.0% | -9.9% | 9 | 10/25 |

## Config 6

```
coverage_q_call=0.8403908597305417, coverage_q_put=0.841321904072538, credit_threshold_frac=0.34109776467084885, defense=close_side_eod, ema_len=34, hysteresis=0.25, long_call_offset_days=15, long_put_offset_days=8, long_strike_offset=70.0, min_credit_frac=0.005062790587544441, regime_action=bull_only, require_credit=True, risk_definition=scenario, risk_fraction=0.1, short_call_delta=0.16459472225978972, short_put_delta=0.37866099351085725, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 68,304 | 65,357 | 33.1% | 34.6% | -8.6% | 0 | 8/25 |
| close_tested_side/immediate | 99,167 | 82,951 | 1.3% | 17.2% | -6.9% | 27 | 15/55 |
| buy_back_short/immediate | 100,975 | 80,132 | 14.7% | 24.3% | -8.5% | 27 | 15/57 |
| roll_out/immediate | 77,194 | 58,847 | 23.8% | 41.2% | -9.4% | 20 | 15/42 |
| roll_out_away/immediate | 83,892 | 58,759 | 17.0% | 41.2% | -8.1% | 23 | 15/45 |
| convert_vertical/immediate | 98,632 | 81,725 | 3.6% | 19.3% | -7.0% | 27 | 15/57 |
| close_all/immediate | 98,865 | 76,630 | 1.5% | 23.4% | -7.4% | 27 | 15/48 |
| delta_hedge/immediate | 74,529 | 65,183 | 30.7% | 70.5% | -20.8% | 23 | 8/28 |
| close_tested_side/t-1 | 78,260 | 53,502 | 23.6% | 46.5% | -11.2% | 17 | 14/40 |
| buy_back_short/t-1 | 83,022 | 46,343 | 24.2% | 53.7% | -12.5% | 17 | 14/41 |

## Config 7

```
coverage_q_call=0.9206584050320089, coverage_q_put=0.9140663497149945, credit_threshold_frac=0.3002717219293118, defense=none, ema_len=34, hysteresis=0.25, long_call_offset_days=19, long_put_offset_days=16, long_strike_offset=95.0, min_credit_frac=0.10324243661016226, regime_action=retracement_only, require_credit=True, risk_definition=scenario, risk_fraction=0.15, short_call_delta=0.46428261217661204, short_put_delta=0.4849129782989621, strike_family=delta, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 98,177 | 69,634 | 4.4% | 33.4% | -6.3% | 0 | 3/23 |
| close_tested_side/immediate | 99,934 | 93,832 | 0.8% | 6.7% | -3.0% | 30 | 8/51 |
| buy_back_short/immediate | 98,552 | 84,066 | 2.9% | 21.3% | -6.1% | 30 | 8/52 |
| roll_out/immediate | 96,614 | 72,645 | 5.2% | 30.3% | -6.2% | 30 | 8/51 |
| roll_out_away/immediate | 98,982 | 86,036 | 3.2% | 20.3% | -6.1% | 30 | 8/52 |
| convert_vertical/immediate | 100,943 | 85,491 | 0.8% | 16.8% | -3.7% | 30 | 8/50 |
| close_all/immediate | 102,392 | 100,100 | 1.7% | 9.1% | -3.0% | 30 | 8/49 |
| delta_hedge/immediate | 94,533 | 101,892 | 11.1% | 96.5% | -63.5% | 21 | 3/16 |
| close_tested_side/t-1 | 101,720 | 88,483 | 1.1% | 14.2% | -2.8% | 23 | 6/44 |
| buy_back_short/t-1 | 102,095 | 80,930 | 2.4% | 24.3% | -6.3% | 23 | 6/45 |
