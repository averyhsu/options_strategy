# P4–P6 v2 SYNTHETIC re-runs — percentile-band family (2026-08-10 amendment)

**SYNTHETIC DATA THROUGHOUT.** These re-runs validate the Pass-1 machinery
with the amended §8.1 space (18 dims; percentile-band strike family as the
DEFAULT arm, free-delta as fallback). Real-data runs remain Pass 2. Tags:
`rerun/p4-percentile`, `rerun/p5-percentile`, `rerun/p6-percentile`.

## P4 v2 — coarse sweep (`experiments/p4v2/`)

16,384 Sobol configs, seed 20260810, same 10y world as v1.

- **0 survivors** (again): the §9.1 weekly-WR floor (0.75) binds for BOTH
  families — the same honest discrimination v1 made.
- The percentile family's traded configs sit **closer to the trader's
  fingerprint** than free-delta: median win magnitude 0.251 (inside the F14
  band [0.15, 0.45]) vs 0.195; positive expectancy 42.8% vs 30.0%.
- **Structural finding:** percentile-band strikes never price as credits on
  the synthetic surface — **0/4,096** credit-required percentile configs ever
  traded (vs 17/4,096 for delta). The author's stated combination (band
  strikes + resting credit orders ≥ ~30% of risk) does not exist on this
  surface; whether real chains offer it is exactly the Pass-2 credit
  verification flagged by `reports/candle_study.md` item (c).

## P5 v2 — intraday defense grids (`experiments/p5v2/`, `experiments/p5v2_percentile/`)

New world `p5-world-intraday-v2-synthetic` (QA CLEAN): identical scripted gap
and crash windows plus ~2 years of EOD pre-history so band warm-up completes.

- Main grid (WR-ranked selection, 8 configs — all delta on this surface,
  160 runs): the v1 defense hierarchy replicates — immediate
  `close_tested_side` / `close_all` dominate drawdown control; `delta_hedge`
  remains pathological through the gap week at MID fills.
- Percentile companion (4 configs, 80 runs, `eod_immediate` entries because
  debit structures cannot rest at credit limits): family exercises the full
  Track-B intraday defense machinery; defense fires rarely (wide bands —
  consistent with the candle study's touch rates at high q);
  `close_tested_side` again the best DD reducer; `delta_hedge` again the
  tail-risk outlier (43% maxDD through the gap).

## P6 v2 — mystery gate + robustness (`experiments/p6v2/`)

- **Mystery gate: PASS.** Hidden config (idx 145, delta family,
  require_credit=False, close_side_eod) recovered as a region: DD-date hard
  constraint filters 16,384 → 60; truth covered on **all 18 dimensions**;
  2 honestly identified (`require_credit`, `regime_action` — both exact),
  16 plateaus. The categorical "identified" label was tightened during this
  run (strict-subset rule; ASSUMPTIONS.md 2026-08-11).
- Robustness on the 330 kept configs: **DSR 0.210**, **PBO 0.505**, WFO
  median OOS profitable share 0.394, block-bootstrap P(NAV<50%) ≈ 21% @1y /
  58% @3y, fees ×1..×3 immaterial at SPX scale. Same verdict as v1: nothing
  on this surface survives deflation; selection is indistinguishable from
  luck. Gap-injector evidence from v1 stands (its explicit-legs machinery is
  family-agnostic and unchanged).

**No real-market conclusion is implied anywhere above.** The machinery —
including the new default family end-to-end — is validated and waiting for
Pass-2 data.
