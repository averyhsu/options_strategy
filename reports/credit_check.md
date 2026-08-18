# Credit check — FULL six-regime, REAL DATA (ThetaData STANDARD), 15:45 ET basis

51-date mini-purchase spec slice; dual credit/debit reading (PLAN §1.6
2026-08-16), ATM reference, 7d + 14d fronts, exit_mode {hold_to_expiry,
exit_at_7dte} on 14d fronts (2026-08-18 amendment). Spot and rates
context are parity-derived (no index subscription). Sensitivity cut per
2026-08-18 amendment. Not investment advice.

- data_version: `theta_slice_v1`
- entry Fridays priced: 51 of 51 (skipped: 0 [])
- structures priced: 1836
- sensitivity cut removes 1 entry dates (median parity RMSE > 1.0 pt)

## VERDICT

1. **Credit reading:** 1.7% of all 1836 structures priced as net credits at the 15:45 ET NBBO mid. The author's claim under the credit reading is **refuted on real chains** (consistent with the synthetic 0/4096 and the EOD preview 0/552).
2. **Return-on-risk reading (author-consistent corner: 14d fronts, q90/q95/atm_ref, offsets 0-50, either exit mode):**
- calm-2017: 1.0 of 6 entry dates reach +30%R in the corner
- volmageddon-feb-2018: 1.0 of 5 entry dates reach +30%R in the corner
- covid-mar-2020: 1.0 of 7 entry dates reach +30%R in the corner
- bear-2022: 1.0 of 10 entry dates reach +30%R in the corner
3. **CONTINUE/PAUSE gate:** 0 of 4 new regimes below 20% → **CONTINUE**.

## Aggregates by regime window

### bear-2022 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 10 | 0.000 | -1.000 | 0.147 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 10 | 0.000 | -0.744 | 0.146 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 10 | 0.000 | -0.502 | 0.144 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 10 | 0.000 | -1.000 | 0.108 | 0.000 |
| 14d | exit_at_7dte | q85 | 25.000 | 10 | 0.000 | -0.733 | 0.102 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 10 | 0.000 | -0.516 | 0.098 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 10 | 0.000 | -1.000 | 0.088 | 0.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 10 | 0.000 | -0.726 | 0.084 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 10 | 0.000 | -0.499 | 0.081 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 10 | 0.000 | -1.000 | 0.074 | 0.000 |
| 14d | exit_at_7dte | q95 | 25.000 | 10 | 0.000 | -0.693 | 0.062 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 10 | 0.000 | -0.504 | 0.064 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 10 | 0.000 | -1.000 | 0.888 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 10 | 0.000 | -0.744 | 0.881 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 10 | 0.000 | -0.502 | 0.861 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 10 | 0.000 | -1.000 | 0.382 | 0.800 |
| 14d | hold_to_expiry | q85 | 25.000 | 10 | 0.000 | -0.733 | 0.352 | 0.700 |
| 14d | hold_to_expiry | q85 | 50.000 | 10 | 0.000 | -0.516 | 0.345 | 0.600 |
| 14d | hold_to_expiry | q90 | 0.000 | 10 | 0.000 | -1.000 | 0.387 | 0.900 |
| 14d | hold_to_expiry | q90 | 25.000 | 10 | 0.000 | -0.726 | 0.374 | 0.800 |
| 14d | hold_to_expiry | q90 | 50.000 | 10 | 0.000 | -0.499 | 0.330 | 0.700 |
| 14d | hold_to_expiry | q95 | 0.000 | 10 | 0.000 | -1.000 | 0.483 | 0.900 |
| 14d | hold_to_expiry | q95 | 25.000 | 10 | 0.000 | -0.693 | 0.407 | 0.900 |
| 14d | hold_to_expiry | q95 | 50.000 | 10 | 0.000 | -0.504 | 0.389 | 0.800 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 10 | 0.000 | -1.000 | 0.476 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 10 | 0.000 | -0.793 | 0.472 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 10 | 0.000 | -0.595 | 0.459 | 1.000 |
| 7d | hold_to_expiry | q85 | 0.000 | 10 | 0.000 | -1.000 | 0.185 | 0.100 |
| 7d | hold_to_expiry | q85 | 25.000 | 10 | 0.000 | -0.779 | 0.177 | 0.100 |
| 7d | hold_to_expiry | q85 | 50.000 | 10 | 0.000 | -0.601 | 0.163 | 0.100 |
| 7d | hold_to_expiry | q90 | 0.000 | 10 | 0.000 | -1.000 | 0.198 | 0.100 |
| 7d | hold_to_expiry | q90 | 25.000 | 10 | 0.000 | -0.772 | 0.184 | 0.100 |
| 7d | hold_to_expiry | q90 | 50.000 | 10 | 0.000 | -0.594 | 0.168 | 0.100 |
| 7d | hold_to_expiry | q95 | 0.000 | 10 | 0.000 | -1.000 | 0.222 | 0.300 |
| 7d | hold_to_expiry | q95 | 25.000 | 10 | 0.000 | -0.768 | 0.206 | 0.200 |
| 7d | hold_to_expiry | q95 | 50.000 | 10 | 0.000 | -0.567 | 0.192 | 0.100 |

### calm-2017 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 6 | 0.000 | -1.000 | 0.115 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 6 | 0.167 | -0.106 | 0.106 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 6 | 1.000 | 0.197 | 0.088 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 6 | 0.000 | -1.000 | 0.203 | 0.167 |
| 14d | exit_at_7dte | q85 | 25.000 | 6 | 0.000 | -0.185 | 0.029 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 6 | 0.000 | -0.066 | 0.012 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 6 | 0.000 | -1.000 | 0.446 | 1.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 6 | 0.000 | -0.184 | 0.061 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 6 | 0.000 | -0.068 | 0.016 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 6 | 0.000 | -1.000 | 1.318 | 1.000 |
| 14d | exit_at_7dte | q95 | 25.000 | 6 | 0.000 | -0.141 | 0.136 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 6 | 0.000 | -0.057 | 0.034 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 6 | 0.000 | -1.000 | 0.627 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 6 | 0.167 | -0.106 | 0.537 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 6 | 1.000 | 0.197 | 0.413 | 0.833 |
| 14d | hold_to_expiry | q85 | 0.000 | 6 | 0.000 | -1.000 | 0.859 | 1.000 |
| 14d | hold_to_expiry | q85 | 25.000 | 6 | 0.000 | -0.185 | 0.271 | 0.167 |
| 14d | hold_to_expiry | q85 | 50.000 | 6 | 0.000 | -0.066 | 0.117 | 0.000 |
| 14d | hold_to_expiry | q90 | 0.000 | 6 | 0.000 | -1.000 | 1.435 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 6 | 0.000 | -0.184 | 0.354 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 6 | 0.000 | -0.068 | 0.143 | 0.000 |
| 14d | hold_to_expiry | q95 | 0.000 | 6 | 0.000 | -1.000 | 3.212 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 6 | 0.000 | -0.141 | 0.515 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 6 | 0.000 | -0.057 | 0.209 | 0.000 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 6 | 0.000 | -1.000 | 0.395 | 0.500 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 6 | 0.000 | -0.224 | 0.326 | 0.500 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 6 | 0.833 | 0.069 | 0.234 | 0.333 |
| 7d | hold_to_expiry | q85 | 0.000 | 6 | 0.000 | -1.000 | 0.799 | 1.000 |
| 7d | hold_to_expiry | q85 | 25.000 | 6 | 0.000 | -0.218 | 0.215 | 0.167 |
| 7d | hold_to_expiry | q85 | 50.000 | 6 | 0.000 | -0.077 | 0.086 | 0.000 |
| 7d | hold_to_expiry | q90 | 0.000 | 6 | 0.000 | -1.000 | 1.085 | 1.000 |
| 7d | hold_to_expiry | q90 | 25.000 | 6 | 0.000 | -0.183 | 0.289 | 0.333 |
| 7d | hold_to_expiry | q90 | 50.000 | 6 | 0.000 | -0.068 | 0.113 | 0.000 |
| 7d | hold_to_expiry | q95 | 0.000 | 6 | 0.000 | -1.000 | 2.484 | 1.000 |
| 7d | hold_to_expiry | q95 | 25.000 | 6 | 0.000 | -0.152 | 0.392 | 1.000 |
| 7d | hold_to_expiry | q95 | 50.000 | 6 | 0.000 | -0.057 | 0.151 | 0.000 |

### covid-mar-2020 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 7 | 0.000 | -1.000 | 0.299 | 0.429 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 7 | 0.000 | -0.719 | 0.298 | 0.429 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 7 | 0.143 | -0.428 | 0.295 | 0.429 |
| 14d | exit_at_7dte | q85 | 0.000 | 7 | 0.000 | -1.000 | 0.287 | 0.429 |
| 14d | exit_at_7dte | q85 | 25.000 | 7 | 0.000 | -0.692 | 0.281 | 0.429 |
| 14d | exit_at_7dte | q85 | 50.000 | 7 | 0.000 | -0.485 | 0.273 | 0.286 |
| 14d | exit_at_7dte | q90 | 0.000 | 7 | 0.000 | -1.000 | 0.284 | 0.429 |
| 14d | exit_at_7dte | q90 | 25.000 | 7 | 0.000 | -0.690 | 0.275 | 0.429 |
| 14d | exit_at_7dte | q90 | 50.000 | 7 | 0.000 | -0.490 | 0.266 | 0.286 |
| 14d | exit_at_7dte | q95 | 0.000 | 7 | 0.000 | -1.000 | 0.331 | 0.571 |
| 14d | exit_at_7dte | q95 | 25.000 | 7 | 0.000 | -0.691 | 0.263 | 0.429 |
| 14d | exit_at_7dte | q95 | 50.000 | 7 | 0.000 | -0.518 | 0.235 | 0.143 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 7 | 0.000 | -1.000 | 1.684 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 7 | 0.000 | -0.719 | 1.673 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 7 | 0.143 | -0.428 | 1.648 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 7 | 0.000 | -1.000 | 1.229 | 1.000 |
| 14d | hold_to_expiry | q85 | 25.000 | 7 | 0.000 | -0.692 | 1.200 | 1.000 |
| 14d | hold_to_expiry | q85 | 50.000 | 7 | 0.000 | -0.485 | 1.162 | 1.000 |
| 14d | hold_to_expiry | q90 | 0.000 | 7 | 0.000 | -1.000 | 1.152 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 7 | 0.000 | -0.690 | 1.110 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 7 | 0.000 | -0.490 | 1.070 | 1.000 |
| 14d | hold_to_expiry | q95 | 0.000 | 7 | 0.000 | -1.000 | 1.248 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 7 | 0.000 | -0.691 | 0.977 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 7 | 0.000 | -0.518 | 0.870 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 7 | 0.000 | -1.000 | 0.960 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 7 | 0.000 | -0.778 | 0.955 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 7 | 0.000 | -0.559 | 0.942 | 1.000 |
| 7d | hold_to_expiry | q85 | 0.000 | 7 | 0.000 | -1.000 | 0.655 | 0.857 |
| 7d | hold_to_expiry | q85 | 25.000 | 7 | 0.000 | -0.758 | 0.638 | 0.857 |
| 7d | hold_to_expiry | q85 | 50.000 | 7 | 0.000 | -0.570 | 0.623 | 0.857 |
| 7d | hold_to_expiry | q90 | 0.000 | 7 | 0.000 | -1.000 | 0.582 | 1.000 |
| 7d | hold_to_expiry | q90 | 25.000 | 7 | 0.000 | -0.762 | 0.566 | 0.857 |
| 7d | hold_to_expiry | q90 | 50.000 | 7 | 0.000 | -0.569 | 0.556 | 0.857 |
| 7d | hold_to_expiry | q95 | 0.000 | 7 | 0.000 | -1.000 | 0.697 | 1.000 |
| 7d | hold_to_expiry | q95 | 25.000 | 7 | 0.000 | -0.771 | 0.512 | 1.000 |
| 7d | hold_to_expiry | q95 | 50.000 | 7 | 0.000 | -0.578 | 0.503 | 1.000 |

### live-window-2026 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 18 | 0.000 | -0.959 | 0.118 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 18 | 0.000 | -0.776 | 0.122 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 18 | 0.000 | -0.568 | 0.123 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 18 | 0.000 | -0.925 | 0.085 | 0.000 |
| 14d | exit_at_7dte | q85 | 25.000 | 18 | 0.000 | -0.716 | 0.065 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 18 | 0.000 | -0.530 | 0.049 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 18 | 0.000 | -0.936 | 0.109 | 0.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 18 | 0.000 | -0.710 | 0.077 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 18 | 0.000 | -0.520 | 0.040 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 18 | 0.000 | -0.866 | 0.207 | 0.167 |
| 14d | exit_at_7dte | q95 | 25.000 | 18 | 0.000 | -0.667 | 0.118 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 18 | 0.000 | -0.464 | 0.071 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 18 | 0.000 | -0.959 | 0.727 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 18 | 0.000 | -0.776 | 0.746 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 18 | 0.000 | -0.568 | 0.734 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 18 | 0.000 | -0.925 | 0.322 | 0.611 |
| 14d | hold_to_expiry | q85 | 25.000 | 18 | 0.000 | -0.716 | 0.279 | 0.389 |
| 14d | hold_to_expiry | q85 | 50.000 | 18 | 0.000 | -0.530 | 0.248 | 0.278 |
| 14d | hold_to_expiry | q90 | 0.000 | 18 | 0.000 | -0.936 | 0.447 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 18 | 0.000 | -0.710 | 0.375 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 18 | 0.000 | -0.520 | 0.328 | 0.667 |
| 14d | hold_to_expiry | q95 | 0.000 | 18 | 0.000 | -0.866 | 0.905 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 18 | 0.000 | -0.667 | 0.715 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 18 | 0.000 | -0.464 | 0.557 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 18 | 0.000 | -0.966 | 0.392 | 0.889 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 18 | 0.000 | -0.817 | 0.391 | 0.889 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 18 | 0.000 | -0.644 | 0.390 | 0.889 |
| 7d | hold_to_expiry | q85 | 0.000 | 18 | 0.000 | -0.959 | 0.159 | 0.000 |
| 7d | hold_to_expiry | q85 | 25.000 | 18 | 0.000 | -0.773 | 0.125 | 0.000 |
| 7d | hold_to_expiry | q85 | 50.000 | 18 | 0.000 | -0.608 | 0.117 | 0.000 |
| 7d | hold_to_expiry | q90 | 0.000 | 18 | 0.000 | -0.952 | 0.215 | 0.222 |
| 7d | hold_to_expiry | q90 | 25.000 | 18 | 0.000 | -0.759 | 0.196 | 0.111 |
| 7d | hold_to_expiry | q90 | 50.000 | 18 | 0.000 | -0.573 | 0.174 | 0.000 |
| 7d | hold_to_expiry | q95 | 0.000 | 18 | 0.000 | -0.941 | 0.458 | 0.944 |
| 7d | hold_to_expiry | q95 | 25.000 | 18 | 0.000 | -0.716 | 0.411 | 0.944 |
| 7d | hold_to_expiry | q95 | 50.000 | 18 | 0.000 | -0.516 | 0.337 | 0.778 |

### vix-spike-aug-2024 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 5 | 0.000 | -0.944 | 0.158 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 5 | 0.000 | -0.700 | 0.157 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 5 | 0.000 | -0.404 | 0.154 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 5 | 0.000 | -0.935 | 0.138 | 0.000 |
| 14d | exit_at_7dte | q85 | 25.000 | 5 | 0.000 | -0.662 | 0.116 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 5 | 0.000 | -0.416 | 0.082 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 5 | 0.000 | -0.909 | 0.135 | 0.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 5 | 0.000 | -0.638 | 0.122 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 5 | 0.000 | -0.392 | 0.068 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 5 | 0.000 | -0.837 | 0.236 | 0.400 |
| 14d | exit_at_7dte | q95 | 25.000 | 5 | 0.000 | -0.640 | 0.141 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 5 | 0.000 | -0.361 | 0.075 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 5 | 0.000 | -0.944 | 0.966 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 5 | 0.000 | -0.700 | 0.959 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 5 | 0.000 | -0.404 | 0.933 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 5 | 0.000 | -0.935 | 0.420 | 0.800 |
| 14d | hold_to_expiry | q85 | 25.000 | 5 | 0.000 | -0.662 | 0.364 | 0.600 |
| 14d | hold_to_expiry | q85 | 50.000 | 5 | 0.000 | -0.416 | 0.318 | 0.600 |
| 14d | hold_to_expiry | q90 | 0.000 | 5 | 0.000 | -0.909 | 0.491 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 5 | 0.000 | -0.638 | 0.389 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 5 | 0.000 | -0.392 | 0.338 | 0.600 |
| 14d | hold_to_expiry | q95 | 0.000 | 5 | 0.000 | -0.837 | 0.688 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 5 | 0.000 | -0.640 | 0.668 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 5 | 0.000 | -0.361 | 0.503 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 5 | 0.000 | -1.000 | 0.649 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 5 | 0.000 | -0.760 | 0.642 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 5 | 0.000 | -0.538 | 0.627 | 0.800 |
| 7d | hold_to_expiry | q85 | 0.000 | 5 | 0.000 | -1.000 | 0.270 | 0.200 |
| 7d | hold_to_expiry | q85 | 25.000 | 5 | 0.000 | -0.713 | 0.238 | 0.200 |
| 7d | hold_to_expiry | q85 | 50.000 | 5 | 0.000 | -0.481 | 0.200 | 0.000 |
| 7d | hold_to_expiry | q90 | 0.000 | 5 | 0.000 | -1.000 | 0.275 | 0.400 |
| 7d | hold_to_expiry | q90 | 25.000 | 5 | 0.000 | -0.688 | 0.243 | 0.200 |
| 7d | hold_to_expiry | q90 | 50.000 | 5 | 0.000 | -0.463 | 0.205 | 0.000 |
| 7d | hold_to_expiry | q95 | 0.000 | 5 | 0.000 | -0.946 | 0.540 | 1.000 |
| 7d | hold_to_expiry | q95 | 25.000 | 5 | 0.000 | -0.599 | 0.358 | 0.600 |
| 7d | hold_to_expiry | q95 | 50.000 | 5 | 0.000 | -0.428 | 0.296 | 0.400 |

### vix-spike-aug-2024 — sensitivity cut (parity RMSE <= 1.0)

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 4 | 0.000 | -0.972 | 0.132 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 4 | 0.000 | -0.710 | 0.129 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 4 | 0.000 | -0.410 | 0.128 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 4 | 0.000 | -0.937 | 0.107 | 0.000 |
| 14d | exit_at_7dte | q85 | 25.000 | 4 | 0.000 | -0.679 | 0.105 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 4 | 0.000 | -0.445 | 0.072 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 4 | 0.000 | -0.904 | 0.130 | 0.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 4 | 0.000 | -0.673 | 0.127 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 4 | 0.000 | -0.406 | 0.066 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 4 | 0.000 | -0.735 | 0.217 | 0.500 |
| 14d | exit_at_7dte | q95 | 25.000 | 4 | 0.000 | -0.607 | 0.140 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 4 | 0.000 | -0.416 | 0.087 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 4 | 0.000 | -0.972 | 0.829 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 4 | 0.000 | -0.710 | 0.808 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 4 | 0.000 | -0.410 | 0.796 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 4 | 0.000 | -0.937 | 0.378 | 0.750 |
| 14d | hold_to_expiry | q85 | 25.000 | 4 | 0.000 | -0.679 | 0.324 | 0.500 |
| 14d | hold_to_expiry | q85 | 50.000 | 4 | 0.000 | -0.445 | 0.278 | 0.500 |
| 14d | hold_to_expiry | q90 | 0.000 | 4 | 0.000 | -0.904 | 0.464 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 4 | 0.000 | -0.673 | 0.400 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 4 | 0.000 | -0.406 | 0.315 | 0.500 |
| 14d | hold_to_expiry | q95 | 0.000 | 4 | 0.000 | -0.735 | 0.687 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 4 | 0.000 | -0.607 | 0.653 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 4 | 0.000 | -0.416 | 0.517 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 4 | 0.000 | -1.000 | 0.491 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 4 | 0.000 | -0.761 | 0.485 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 4 | 0.000 | -0.539 | 0.472 | 0.750 |
| 7d | hold_to_expiry | q85 | 0.000 | 4 | 0.000 | -0.978 | 0.215 | 0.000 |
| 7d | hold_to_expiry | q85 | 25.000 | 4 | 0.000 | -0.717 | 0.179 | 0.000 |
| 7d | hold_to_expiry | q85 | 50.000 | 4 | 0.000 | -0.503 | 0.156 | 0.000 |
| 7d | hold_to_expiry | q90 | 0.000 | 4 | 0.000 | -0.956 | 0.265 | 0.250 |
| 7d | hold_to_expiry | q90 | 25.000 | 4 | 0.000 | -0.686 | 0.234 | 0.000 |
| 7d | hold_to_expiry | q90 | 50.000 | 4 | 0.000 | -0.469 | 0.201 | 0.000 |
| 7d | hold_to_expiry | q95 | 0.000 | 4 | 0.000 | -0.973 | 0.445 | 1.000 |
| 7d | hold_to_expiry | q95 | 25.000 | 4 | 0.000 | -0.645 | 0.323 | 0.500 |
| 7d | hold_to_expiry | q95 | 50.000 | 4 | 0.000 | -0.444 | 0.284 | 0.250 |

### volmageddon-feb-2018 — all entry dates

| front_variant | exit_mode | label | wing_offset | n | frac_credit | med_net_prem_pct_risk | med_max_gain_pct_risk | frac_30pct_ok |
|---|---|---|---|---|---|---|---|---|
| 14d | exit_at_7dte | atm_ref | 0.000 | 5 | 0.000 | -1.000 | 0.189 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 25.000 | 5 | 0.000 | -0.283 | 0.175 | 0.000 |
| 14d | exit_at_7dte | atm_ref | 50.000 | 5 | 1.000 | 0.152 | 0.153 | 0.000 |
| 14d | exit_at_7dte | q85 | 0.000 | 5 | 0.000 | -1.000 | 0.148 | 0.000 |
| 14d | exit_at_7dte | q85 | 25.000 | 5 | 0.000 | -0.353 | 0.101 | 0.000 |
| 14d | exit_at_7dte | q85 | 50.000 | 5 | 0.000 | -0.120 | 0.078 | 0.000 |
| 14d | exit_at_7dte | q90 | 0.000 | 5 | 0.000 | -1.000 | 0.165 | 0.000 |
| 14d | exit_at_7dte | q90 | 25.000 | 5 | 0.000 | -0.334 | 0.070 | 0.000 |
| 14d | exit_at_7dte | q90 | 50.000 | 5 | 0.000 | -0.133 | 0.057 | 0.000 |
| 14d | exit_at_7dte | q95 | 0.000 | 5 | 0.000 | -0.768 | 0.243 | 0.200 |
| 14d | exit_at_7dte | q95 | 25.000 | 5 | 0.000 | -0.295 | 0.119 | 0.000 |
| 14d | exit_at_7dte | q95 | 50.000 | 5 | 0.000 | -0.169 | 0.044 | 0.000 |
| 14d | hold_to_expiry | atm_ref | 0.000 | 5 | 0.000 | -1.000 | 1.073 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 25.000 | 5 | 0.000 | -0.283 | 0.989 | 1.000 |
| 14d | hold_to_expiry | atm_ref | 50.000 | 5 | 1.000 | 0.152 | 0.841 | 1.000 |
| 14d | hold_to_expiry | q85 | 0.000 | 5 | 0.000 | -1.000 | 0.790 | 1.000 |
| 14d | hold_to_expiry | q85 | 25.000 | 5 | 0.000 | -0.353 | 0.435 | 1.000 |
| 14d | hold_to_expiry | q85 | 50.000 | 5 | 0.000 | -0.120 | 0.325 | 0.600 |
| 14d | hold_to_expiry | q90 | 0.000 | 5 | 0.000 | -1.000 | 0.899 | 1.000 |
| 14d | hold_to_expiry | q90 | 25.000 | 5 | 0.000 | -0.334 | 0.516 | 1.000 |
| 14d | hold_to_expiry | q90 | 50.000 | 5 | 0.000 | -0.133 | 0.331 | 0.600 |
| 14d | hold_to_expiry | q95 | 0.000 | 5 | 0.000 | -0.768 | 1.142 | 1.000 |
| 14d | hold_to_expiry | q95 | 25.000 | 5 | 0.000 | -0.295 | 0.619 | 1.000 |
| 14d | hold_to_expiry | q95 | 50.000 | 5 | 0.000 | -0.169 | 0.384 | 0.800 |
| 7d | hold_to_expiry | atm_ref | 0.000 | 5 | 0.000 | -1.000 | 0.533 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 25.000 | 5 | 0.000 | -0.446 | 0.496 | 1.000 |
| 7d | hold_to_expiry | atm_ref | 50.000 | 5 | 0.200 | -0.083 | 0.423 | 1.000 |
| 7d | hold_to_expiry | q85 | 0.000 | 5 | 0.000 | -1.000 | 0.448 | 0.600 |
| 7d | hold_to_expiry | q85 | 25.000 | 5 | 0.000 | -0.445 | 0.225 | 0.400 |
| 7d | hold_to_expiry | q85 | 50.000 | 5 | 0.000 | -0.201 | 0.170 | 0.200 |
| 7d | hold_to_expiry | q90 | 0.000 | 5 | 0.000 | -1.000 | 0.507 | 1.000 |
| 7d | hold_to_expiry | q90 | 25.000 | 5 | 0.000 | -0.434 | 0.292 | 0.400 |
| 7d | hold_to_expiry | q90 | 50.000 | 5 | 0.000 | -0.194 | 0.194 | 0.200 |
| 7d | hold_to_expiry | q95 | 0.000 | 5 | 0.000 | -1.000 | 0.687 | 1.000 |
| 7d | hold_to_expiry | q95 | 25.000 | 5 | 0.000 | -0.380 | 0.450 | 1.000 |
| 7d | hold_to_expiry | q95 | 50.000 | 5 | 0.000 | -0.181 | 0.240 | 0.400 |
