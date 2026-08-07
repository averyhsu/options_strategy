# P5 intraday defense grid — SYNTHETIC world

**SYNTHETIC DATA** (`synthetic-936f6f29f7e1`) — Pass-1 dress rehearsal: near-miss P4
configs (selection rule in eval/p5_grid.py) run through the REAL Track-B
engine with resting EV-gated entries and intraday touch monitoring.
Fill-model bounds reported side-by-side per PLAN §7.2 (CONSERVATIVE = lower
bound; MID = central; OPTIMISTIC never headlines).

## Config 0

```
credit_threshold_frac=0.3364225149154663, defense=close_side_eod, ema_len=13, hysteresis=0.5, long_call_offset_days=7, long_put_offset_days=11, long_strike_offset=100.0, min_credit_frac=0.011864318326115609, regime_action=retracement_only, require_credit=True, risk_definition=scenario, risk_fraction=0.1, short_call_delta=0.34309540279209616, short_put_delta=0.463021005410701, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 122,674 | 144,615 | 10.3% | 13.0% | -7.7% | 0 | 6/8 |
| close_tested_side/immediate | 90,396 | 91,560 | 10.2% | 10.2% | -2.4% | 12 | 17/18 |
| buy_back_short/immediate | 86,036 | 116,801 | 14.0% | 11.7% | -3.2% | 11 | 14/16 |
| roll_out/immediate | 127,321 | 150,016 | 8.1% | 12.6% | -7.4% | 14 | 17/21 |
| roll_out_away/immediate | 118,282 | 87,059 | 11.5% | 12.9% | -2.5% | 11 | 17/16 |
| convert_vertical/immediate | 87,543 | 87,643 | 13.2% | 13.1% | -4.1% | 6 | 9/9 |
| close_all/immediate | 68,177 | 69,166 | 32.3% | 31.3% | -25.0% | 14 | 17/21 |
| delta_hedge/immediate | 124,487 | 136,503 | 81.0% | 158.2% | -160.7% | 14 | 6/8 |
| close_tested_side/t-1 | 120,401 | 115,493 | 12.3% | 11.9% | -3.5% | 7 | 10/12 |
| buy_back_short/t-1 | 122,156 | 142,754 | 10.6% | 13.2% | -7.8% | 7 | 8/12 |

## Config 1

```
credit_threshold_frac=0.28254845179617405, defense=close_side_eod, ema_len=34, hysteresis=0.5, long_call_offset_days=14, long_put_offset_days=9, long_strike_offset=70.0, min_credit_frac=0.05988259240984917, regime_action=bull_only, require_credit=True, risk_definition=margin, risk_fraction=0.1, short_call_delta=0.38642507917247715, short_put_delta=0.31658761892467735, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 93,198 | 99,752 | 7.8% | 6.4% | -3.9% | 0 | 3/6 |
| close_tested_side/immediate | 97,316 | 97,330 | 2.7% | 3.9% | -2.1% | 5 | 6/11 |
| buy_back_short/immediate | 98,859 | 108,461 | 5.9% | 5.9% | -3.7% | 5 | 6/11 |
| roll_out/immediate | 94,656 | 101,262 | 6.9% | 4.8% | -4.0% | 5 | 6/11 |
| roll_out_away/immediate | 95,971 | 105,895 | 5.5% | 5.2% | -3.8% | 5 | 6/11 |
| convert_vertical/immediate | 92,164 | 93,328 | 7.9% | 7.2% | -4.3% | 5 | 4/9 |
| close_all/immediate | 97,381 | 97,889 | 2.7% | 2.7% | -2.1% | 5 | 6/11 |
| delta_hedge/immediate | 98,114 | 108,783 | 46.1% | 61.4% | -21.4% | 5 | 3/6 |
| close_tested_side/t-1 | 93,198 | 92,851 | 7.8% | 8.4% | -4.3% | 5 | 3/8 |
| buy_back_short/t-1 | 93,198 | 102,250 | 7.8% | 4.9% | -3.9% | 5 | 3/8 |

## Config 2

```
credit_threshold_frac=0.21808069422841073, defense=close_side_eod, ema_len=13, hysteresis=0.25, long_call_offset_days=8, long_put_offset_days=13, long_strike_offset=55.0, min_credit_frac=0.08293217290192843, regime_action=bull_only, require_credit=True, risk_definition=width, risk_fraction=0.1, short_call_delta=0.4956377767957747, short_put_delta=0.33285102229565383, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 98,446 | 93,455 | 9.0% | 8.2% | -7.7% | 0 | 3/6 |
| close_tested_side/immediate | 94,485 | 93,636 | 5.5% | 6.5% | -2.3% | 5 | 7/10 |
| buy_back_short/immediate | 102,957 | 106,833 | 10.3% | 10.2% | -6.8% | 5 | 9/12 |
| roll_out/immediate | 102,718 | 100,229 | 7.4% | 7.8% | -7.2% | 5 | 7/10 |
| roll_out_away/immediate | 101,463 | 100,632 | 7.5% | 9.5% | -7.2% | 5 | 7/12 |
| convert_vertical/immediate | 90,978 | 92,059 | 9.4% | 9.0% | -6.2% | 5 | 9/12 |
| close_all/immediate | 97,681 | 97,297 | 10.5% | 10.5% | -3.5% | 5 | 7/10 |
| delta_hedge/immediate | 108,385 | 104,813 | 52.0% | 40.5% | -13.9% | 5 | 3/6 |
| close_tested_side/t-1 | 99,673 | 98,132 | 9.0% | 10.4% | -4.2% | 4 | 4/7 |
| buy_back_short/t-1 | 97,294 | 100,360 | 9.0% | 7.8% | -7.2% | 4 | 4/7 |

## Config 3

```
credit_threshold_frac=0.2766093030571938, defense=none, ema_len=13, hysteresis=0.25, long_call_offset_days=22, long_put_offset_days=12, long_strike_offset=90.0, min_credit_frac=0.06948251239955426, regime_action=bull_only, require_credit=True, risk_definition=scenario, risk_fraction=0.1, short_call_delta=0.49951496524736283, short_put_delta=0.22130674617365004, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 88,257 | 94,655 | 13.7% | 12.9% | -9.5% | 0 | 3/5 |
| close_tested_side/immediate | 97,057 | 96,730 | 2.9% | 3.3% | -1.9% | 5 | 7/10 |
| buy_back_short/immediate | 93,657 | 101,320 | 13.0% | 12.2% | -9.0% | 5 | 7/10 |
| roll_out/immediate | 89,563 | 94,288 | 13.5% | 13.0% | -9.6% | 5 | 7/10 |
| roll_out_away/immediate | 90,593 | 98,238 | 13.4% | 12.5% | -9.2% | 5 | 7/10 |
| convert_vertical/immediate | 97,451 | 99,324 | 3.1% | 2.6% | -1.2% | 5 | 7/10 |
| close_all/immediate | 97,554 | 97,494 | 4.4% | 4.4% | -1.9% | 5 | 7/10 |
| delta_hedge/immediate | 96,336 | 113,996 | 35.8% | 63.1% | -22.0% | 5 | 3/5 |
| close_tested_side/t-1 | 88,624 | 87,647 | 13.5% | 13.7% | -11.0% | 4 | 4/7 |
| buy_back_short/t-1 | 87,385 | 94,078 | 13.8% | 13.0% | -9.6% | 4 | 4/7 |

## Config 4

```
credit_threshold_frac=0.2683616377413273, defense=none, ema_len=21, hysteresis=0.5, long_call_offset_days=11, long_put_offset_days=8, long_strike_offset=55.0, min_credit_frac=0.06071761101484299, regime_action=any_event, require_credit=True, risk_definition=margin, risk_fraction=0.2, short_call_delta=0.30707175405696036, short_put_delta=0.41500894059427085, threshold_reference=max_gain
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 74,627 | 74,627 | 25.4% | 25.4% | -18.4% | 0 | 5/4 |
| close_tested_side/immediate | 92,754 | 88,143 | 8.3% | 11.9% | -7.6% | 4 | 10/9 |
| buy_back_short/immediate | 88,768 | 82,777 | 22.1% | 22.5% | -10.3% | 4 | 10/9 |
| roll_out/immediate | 82,203 | 79,637 | 19.9% | 21.6% | -18.3% | 4 | 11/10 |
| roll_out_away/immediate | 87,423 | 79,887 | 20.2% | 21.7% | -13.3% | 4 | 11/10 |
| convert_vertical/immediate | 97,820 | 90,558 | 3.5% | 10.8% | -6.5% | 4 | 9/8 |
| close_all/immediate | 107,432 | 102,756 | 2.2% | 8.6% | -5.2% | 4 | 11/9 |
| delta_hedge/immediate | 96,222 | 93,961 | 76.8% | 79.1% | -28.0% | 4 | 5/4 |
| close_tested_side/t-1 | 76,099 | 76,099 | 23.9% | 23.9% | -18.4% | 3 | 6/5 |
| buy_back_short/t-1 | 72,483 | 72,483 | 27.5% | 27.5% | -18.4% | 3 | 6/5 |
