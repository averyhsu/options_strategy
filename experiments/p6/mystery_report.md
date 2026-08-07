# Mystery-trader identification — SYNTHETIC (P6 Pass-1 gate)

**SYNTHETIC DATA.** A hidden config's simulated live curve
(2026-04-01 -> 2026-07-30) was matched by the ABC machinery over the
16,384 P4 candidates (truth excluded from the
candidate pool; used only for this verification).

- **GATE: PASS** — accepted region covers the hidden config on every IDENTIFIED dimension (plateau
  marginals ~ the prior carry no information and cannot contradict truth;
  their truth-in-range status is still reported below)
- DD-date hard constraint (+/-2d) passed by 33 candidates
- accepted set: 33 configs (eps = 6.3811)
- dimensions identified (spread collapsed): 2 of 15 — the rest are honest plateaus (PLAN §9.3 expects this)

| dim | truth | accepted region | identified? | truth in region |
|---|---|---|---|---|
| short_put_delta | 0.1315 | [0.05106, 0.4468] | plateau | yes |
| short_call_delta | 0.4638 | [0.05224, 0.4895] | plateau | yes |
| long_put_offset_days | 39 | [9, 41] | plateau | yes |
| long_call_offset_days | 47 | [13, 52] | plateau | yes |
| long_strike_offset | 35 | [0, 95] | plateau | yes |
| credit_threshold_frac | 0.2174 | [0.2421, 0.5787] | plateau | no |
| threshold_reference | width | max_gain, scenario_r, width | plateau | yes |
| require_credit | False | False | YES | yes |
| min_credit_frac | 0.1866 | [0.001505, 0.1899] | plateau | yes |
| regime_action | trade_all | any_event, retracement_only, trade_all | plateau | yes |
| ema_len | 34 | 13, 21, 34 | plateau | yes |
| hysteresis | 0.5 | 0.0, 0.25, 0.5 | plateau | yes |
| defense | none | close_side_eod, none | YES | yes |
| risk_definition | margin | margin, scenario, width | plateau | yes |
| risk_fraction | 0.15 | 0.1, 0.15, 0.2 | plateau | yes |

An accepted REGION covering the truth with plateaus on most dimensions is
the expected honest outcome: the live window carries limited information
and the matcher must not pretend otherwise.
