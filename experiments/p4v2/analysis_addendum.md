# P4 v2 sweep — family analysis addendum (SYNTHETIC)

**SYNTHETIC DATA.** 18-dim space v2 (percentile-band default family per the
2026-08-10 PLAN amendment), 16,384 Sobol configs, seed 20260810, on the same
10y world as v1. Survivors: **0** — the §9.1 weekly-WR floor (0.75) binds on
this surface for BOTH families, exactly as in v1: an honest discrimination,
not machinery failure.

## Family comparison (traded = >= 30 cycles)

| family | n | traded | WR p90 | WR max | win-mag med | win-mag in [0.15,0.45] | expectancy>0 | maxDD med |
|---|---|---|---|---|---|---|---|---|
| delta | 8,192 | 3,699 | 0.557 | 0.800 | 0.195 | 45.7% | 30.0% | 0.662 |
| percentile | 8,192 | 2,343 | 0.568 | 0.765 | 0.251 | 50.7% | 42.8% | 0.692 |

The percentile family's traded configs sit measurably closer to the trader's
fingerprint than free-delta ones: median win magnitude inside the F14 band
and a higher fraction of positive-expectancy configs. On THIS synthetic
surface neither family reaches the WR floor; whether the percentile family
does so on real chains is a Pass-2 question.

## Near-miss pool for P5 (single prune reason, credit-required)

| family | n |
|---|---|
| delta | 1 |

## coverage_q_put marginal among traded percentile configs

| q bin | n | WR med | win-mag med |
|---|---|---|---|
| 0.80 | 741 | 0.489 | 0.273 |
| 0.85 | 806 | 0.489 | 0.253 |
| 0.90 | 796 | 0.485 | 0.224 |
