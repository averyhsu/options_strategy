# Mystery-trader identification — SYNTHETIC (P6 Pass-1 gate)

**SYNTHETIC DATA.** A hidden config's simulated live curve
(2026-04-01 -> 2026-07-30) was matched by the ABC machinery over the
16,384 P4 candidates (truth excluded from the
candidate pool; used only for this verification).

- **GATE: PASS** — accepted region covers the hidden config on every IDENTIFIED dimension (plateau
  marginals ~ the prior carry no information and cannot contradict truth;
  their truth-in-range status is still reported below)
- DD-date hard constraint (+/-2d) passed by 60 candidates
- accepted set: 60 configs (eps = 5.3640)
- dimensions identified (spread collapsed): 2 of 18 — the rest are honest plateaus (PLAN §9.3 expects this)

| dim | truth | accepted region | identified? | truth in region |
|---|---|---|---|---|
| short_put_delta | 0.2829 | [0.06564, 0.4988] | plateau | yes |
| short_call_delta | 0.1936 | [0.05626, 0.4996] | plateau | yes |
| long_put_offset_days | 8 | [7, 40] | plateau | yes |
| long_call_offset_days | 26 | [13, 50] | plateau | yes |
| long_strike_offset | 85 | [0, 100] | plateau | yes |
| credit_threshold_frac | 0.4614 | [0.2189, 0.5913] | plateau | yes |
| threshold_reference | max_gain | max_gain, scenario_r, width | plateau | yes |
| require_credit | False | False | YES | yes |
| min_credit_frac | 0.05945 | [0.01009, 0.197] | plateau | yes |
| regime_action | trade_all | trade_all | YES | yes |
| ema_len | 34 | 13, 21, 34 | plateau | yes |
| hysteresis | 0.25 | 0.0, 0.25, 0.5 | plateau | yes |
| defense | close_side_eod | close_side_eod, none | plateau | yes |
| risk_definition | margin | margin, scenario, width | plateau | yes |
| risk_fraction | 0.2 | 0.1, 0.15, 0.2 | plateau | yes |
| strike_family | delta | delta, percentile | plateau | yes |
| coverage_q_put | 0.8892 | [0.8005, 0.9483] | plateau | yes |
| coverage_q_call | 0.903 | [0.8006, 0.9485] | plateau | yes |

An accepted REGION covering the truth with plateaus on most dimensions is
the expected honest outcome: the live window carries limited information
and the matcher must not pretend otherwise.
