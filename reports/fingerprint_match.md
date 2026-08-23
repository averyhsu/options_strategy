# ABC fingerprint match — REAL live window vs REAL targets (Pass 2)

Space v4 (21 dims incl. exit_mode) over the REAL 15-min live world (`theta_live_world_v1`, 547 sessions); targets from configs/fingerprints.yaml (IBKR screenshots, PLAN §2). The published record has no daily VAMI path, so the curve-distance term does not bind; the F4 drawdown-date window (±2d) is the hard gate. Not investment advice.

## Summary

- data_version: theta_live_world_v1
- n_candidates: 16384
- n_hard_pass_dd_gate: 0
- eps: inf
- n_accepted: 0
- n_dims_identified: 0
- median_accepted_n_live_cycles: None

## Posterior marginals (accepted set)

| dim | accepted | identified |
|---|---|---|
| short_put_delta | - | plateau |
| short_call_delta | - | plateau |
| long_put_offset_days | - | plateau |
| long_call_offset_days | - | plateau |
| long_strike_offset | - | plateau |
| credit_threshold_frac | - | plateau |
| threshold_reference | - | plateau |
| require_credit | - | plateau |
| min_credit_frac | - | plateau |
| regime_action | - | plateau |
| ema_len | - | plateau |
| hysteresis | - | plateau |
| defense | - | plateau |
| risk_definition | - | plateau |
| risk_fraction | - | plateau |
| strike_family | - | plateau |
| coverage_q_put | - | plateau |
| coverage_q_call | - | plateau |
| wing_family | - | plateau |
| front_dte | - | plateau |
| exit_mode | - | plateau |

## Identifiability statement

0 of 21 dimensions identified (accepted set a strict subset of the prior); the remainder are plateaus — the honest expected outcome per PLAN §9.3. Dims marked YES constitute 'the family that matches'; plateau dims are unconstrained by the published record.

## Zero-acceptance diagnosis (nearest candidates, F4 gate disabled)

| dist | cycles | sharpe | wr | maxDD | dd peak->valley | family | front | exit | defense |
|---|---|---|---|---|---|---|---|---|---|
| 0.61 | 7 | 2.9 | 0.714 | 0.0901 | 2026-05-15->2026-05-20 | percentile | 7 | hold | none |
| 0.61 | 4 | 3.43 | 0.75 | 0.0801 | 2026-05-15->2026-05-20 | delta | 7 | exit_7dte | none |
| 0.65 | 7 | 3.92 | 0.857 | 0.0821 | 2026-05-15->2026-05-20 | percentile | 7 | exit_7dte | none |
| 0.91 | 5 | 2.06 | 0.6 | 0.1346 | 2026-04-01->2026-04-13 | percentile | 7 | exit_7dte | none |
| 0.97 | 2 | 3.45 | 0.5 | 0.0741 | 2026-05-15->2026-05-20 | delta | 7 | exit_7dte | none |
| 1.02 | 2 | 4.11 | 1.0 | 0.0544 | 2026-05-15->2026-05-20 | delta | 7 | exit_7dte | none |
| 1.06 | 6 | 2.33 | 0.5 | 0.1251 | 2026-04-01->2026-04-13 | percentile | 7 | hold | none |
| 1.08 | 4 | 0.84 | 0.75 | 0.1228 | 2026-04-01->2026-04-13 | delta | 7 | exit_7dte | none |
| 1.09 | 0 | 4.33 | None | 0.0712 | 2026-05-15->2026-05-20 | delta | 7 | exit_7dte | none |
| 1.13 | 1 | 2.28 | 1.0 | 0.0821 | 2026-05-15->2026-05-20 | delta | 14 | hold | none |

**Reading:** zero candidates pass the F4 drawdown-date hard gate, and the nearest soft-ranked candidates sit far from the targets on the scalar features as well. On this data and under this model of the family (EOD-mid fills at the 15:45 basis, {none, close-tested-side} defense, dual strike families, 7d/14d fronts with optional exit-at-7dte), NO parameter region reproduces the published live record. Model gaps that could account for the mismatch (not evidence of the record's veracity either way): richer defense/rolling than the collapsed proxy, resting intraday credit-order fills vs EOD-mid, and any non-diagonal activity in the account beyond the acceptance tolerance.
