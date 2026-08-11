# P5 intraday defense grid — SYNTHETIC world

**SYNTHETIC DATA** (`synthetic-b555e1ab2c37`) — Pass-1 dress rehearsal: near-miss P4
configs (selection rule in eval/p5_grid.py) run through the REAL Track-B
engine with resting EV-gated entries and intraday touch monitoring.
Fill-model bounds reported side-by-side per PLAN §7.2 (CONSERVATIVE = lower
bound; MID = central; OPTIMISTIC never headlines).

## Config 0

```
coverage_q_call=0.8134282934945077, coverage_q_put=0.8890227421186865, credit_threshold_frac=0.4100371960550547, defense=close_side_eod, ema_len=21, hysteresis=0.25, long_call_offset_days=45, long_put_offset_days=24, long_strike_offset=5.0, min_credit_frac=0.13791222609579565, regime_action=retracement_only, require_credit=False, risk_definition=scenario, risk_fraction=0.2, short_call_delta=0.44638565634377303, short_put_delta=0.321602185536176, strike_family=percentile, threshold_reference=width
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| close_tested_side/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| buy_back_short/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| roll_out/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| roll_out_away/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| convert_vertical/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| close_all/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| delta_hedge/immediate | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| close_tested_side/t-1 | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |
| buy_back_short/t-1 | 101,066 | 101,066 | 0.8% | 0.8% | -0.5% | 0 | 2/2 |

## Config 1

```
coverage_q_call=0.8653293392620981, coverage_q_put=0.8301565827801825, credit_threshold_frac=0.4193685080856085, defense=none, ema_len=13, hysteresis=0.25, long_call_offset_days=53, long_put_offset_days=10, long_strike_offset=95.0, min_credit_frac=0.043822401948273186, regime_action=retracement_only, require_credit=False, risk_definition=margin, risk_fraction=0.1, short_call_delta=0.25933789382688704, short_put_delta=0.19798244391568004, strike_family=percentile, threshold_reference=scenario_r
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 96,228 | 96,228 | 3.8% | 3.8% | -2.3% | 0 | 2/2 |
| close_tested_side/immediate | 98,362 | 98,362 | 1.6% | 1.6% | -0.8% | 1 | 3/3 |
| buy_back_short/immediate | 97,113 | 97,113 | 2.9% | 2.9% | -1.4% | 1 | 3/3 |
| roll_out/immediate | 97,591 | 97,591 | 3.0% | 3.0% | -2.1% | 1 | 3/3 |
| roll_out_away/immediate | 97,632 | 97,632 | 2.4% | 2.4% | -0.8% | 1 | 3/3 |
| convert_vertical/immediate | 98,292 | 98,292 | 1.7% | 1.7% | -0.8% | 1 | 3/3 |
| close_all/immediate | 96,548 | 96,548 | 3.5% | 3.5% | -2.5% | 1 | 3/3 |
| delta_hedge/immediate | 89,126 | 89,126 | 20.9% | 20.9% | -5.0% | 1 | 1/1 |
| close_tested_side/t-1 | 96,132 | 96,132 | 3.9% | 3.9% | -2.4% | 1 | 3/3 |
| buy_back_short/t-1 | 94,097 | 94,097 | 5.9% | 5.9% | -2.4% | 1 | 2/2 |

## Config 2

```
coverage_q_call=0.8419895913917572, coverage_q_put=0.8070968237239868, credit_threshold_frac=0.4474201131612063, defense=close_side_eod, ema_len=21, hysteresis=0.25, long_call_offset_days=13, long_put_offset_days=35, long_strike_offset=35.0, min_credit_frac=0.07641564067453147, regime_action=retracement_only, require_credit=False, risk_definition=width, risk_fraction=0.15, short_call_delta=0.23822150807827713, short_put_delta=0.30314103164710104, strike_family=percentile, threshold_reference=width
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| close_tested_side/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| buy_back_short/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| roll_out/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| roll_out_away/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| convert_vertical/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| close_all/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| delta_hedge/immediate | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| close_tested_side/t-1 | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |
| buy_back_short/t-1 | 101,236 | 101,236 | 4.6% | 4.6% | -3.4% | 0 | 3/3 |

## Config 3

```
coverage_q_call=0.9023464913479984, coverage_q_put=0.8688712891656906, credit_threshold_frac=0.4477333586663008, defense=close_side_eod, ema_len=13, hysteresis=0.25, long_call_offset_days=10, long_put_offset_days=52, long_strike_offset=70.0, min_credit_frac=0.11296556945890189, regime_action=bull_only, require_credit=False, risk_definition=width, risk_fraction=0.1, short_call_delta=0.25674040322192015, short_put_delta=0.3745775972492993, strike_family=percentile, threshold_reference=width
```

| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) | worst day (MID) | defenses | fills (C/M) |
|---|---|---|---|---|---|---|---|
| none | 84,221 | 84,221 | 26.7% | 26.7% | -7.3% | 0 | 5/5 |
| close_tested_side/immediate | 89,714 | 89,714 | 22.6% | 22.6% | -5.3% | 2 | 6/6 |
| buy_back_short/immediate | 84,666 | 84,666 | 27.9% | 27.9% | -7.3% | 2 | 6/6 |
| roll_out/immediate | 85,623 | 85,623 | 25.5% | 25.5% | -7.2% | 2 | 6/6 |
| roll_out_away/immediate | 85,184 | 85,184 | 27.0% | 27.0% | -7.2% | 2 | 6/6 |
| convert_vertical/immediate | 87,224 | 87,224 | 25.0% | 25.0% | -6.2% | 2 | 6/6 |
| close_all/immediate | 84,221 | 84,221 | 26.7% | 26.7% | -7.3% | 2 | 5/5 |
| delta_hedge/immediate | 118,866 | 118,866 | 43.4% | 43.4% | -31.3% | 2 | 6/6 |
| close_tested_side/t-1 | 88,744 | 88,744 | 22.8% | 22.8% | -5.4% | 2 | 6/6 |
| buy_back_short/t-1 | 81,996 | 81,996 | 28.6% | 28.6% | -7.5% | 2 | 6/6 |
