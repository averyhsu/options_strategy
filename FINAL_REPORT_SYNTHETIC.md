# FINAL REPORT — Pass 1 (SYNTHETIC)

> **SYNTHETIC DATA ONLY.** Every number in this report was produced on
> seeded synthetic worlds (Heston+Merton underlying, SSVI chains). This is
> the full-system dress rehearsal required by PLAN §12.0 Pass 1. **No
> real-market conclusion of any kind is stated or implied.** Pass 2 reruns
> P4-P6 on purchased historical data. A matched configuration is not
> evidence of the original trader's true rules nor of future
> profitability. Nothing here is investment advice.

## Front page (PLAN §10.3)

- **Deflated Sharpe Ratio: 0.186** — best kept config's ann.
  Sharpe 0.70, deflated against N = 16,384
  ledgered trials. Read: on this synthetic surface, the best selected
  config is statistically indistinguishable from selection luck.
- **PBO (CSCV, 16 blocks, 200 splits): 0.32** —
  probability that the in-sample best underperforms the median out of
  sample.

## What was run

- P4 coarse sweep: 16,384 Sobol configs over the PLAN §8 priors on a
  10y EOD world (`synthetic-27add20104b9`): **0 survivors** of the
  fingerprint-informed §9.1 filters (the trader's WR band is the binding
  constraint); 358 kept incl. the 2% random bias-guard.
- P5 intraday grid: 100 Track-B runs (screened configs x
  10 defense variants x CONSERVATIVE/MID) on a 9-week
  5-min world (`synthetic-936f6f29f7e1`) incl. a scripted -5% weekend gap.
- P6 mystery trader: hidden config vs 16,384 candidates —
  **gate PASS**: 33
  candidates survive the DD-date hard constraint; the accepted region
  (33 configs) covers the hidden truth on every identified
  dimension (2 identified, the rest honest plateaus).

## §10(a) Does the family have positive net expectancy, and where?

On THIS synthetic surface: no configuration reproduces the target profile.
2,306 of 7,461 trading configs had positive after-fee expectancy, but with
commodity-like win rates (median 0.47, max 0.78) and small win magnitudes —
never the claimed ~0.85-0.92 WR with +30%-of-R wins. Scripted-regime
slicing (stress table below) shows the profitable segments are grind-up
regimes; the bear-grind segment is ruinous (median -43% for top configs).

## §10(b) Which parameter regions match the fingerprints, and identifiability

The mystery-trader exercise measures exactly this with a KNOWN truth: the
DD-date constraint is extremely informative (16,383 -> 33 candidates); the
posterior identifies `require_credit` and `defense` exactly and leaves 13 of
15 dimensions as plateaus. **Expectation for Pass 2: most structure
parameters will NOT be point-identified from ~87 daily observations; honest
deliverable is the accepted region + plateau statement** (PLAN §9.3).

## §10(c) Do matching regions survive WFO / DSR / PBO / stress?

- Walk-forward (54 anchored+rolling folds, train 3y / test 6m /
  step 3m): median OOS share of top-decile configs profitable = 
  **0.43** — region selection does not
  reliably transfer out of sample here.
- DSR 0.186 and PBO 0.32 (front page).
- Scripted stress windows (top-5 kept configs, median window return):

| window | median | worst |
|---|---|---|
| SCRIPTED-VOL-EVENT-1 | -9.5% | -29.1% |
| SCRIPTED-CRASH | +16.2% | +2.1% |
| SCRIPTED-BEAR-GRIND | -42.8% | -72.7% |
| SCRIPTED-VIX-SPIKE | +6.7% | -5.5% |

- Weekend-gap injector (live explicit-credit structure, MID fills):

| gap | vol mult | undefended | defended (close tested side) |
|---|---|---|---|
| -8% | x4 | -28.7% (worst day -18.8%) | -9.8% |
| -5% | x3 | -26.8% (worst day -15.9%) | -5.7% |
| -3% | x2 | -21.8% (worst day -10.3%) | -2.9% |

Defense truncates gap losses substantially but cannot beat the overnight
jump itself — the F4 lesson; any Pass-2 result without gap stress is
incomplete (PLAN §14).

## §10(d) Tail / risk-of-ruin at the trader's sizing

Block-bootstrap of 17,376 kept-config weekly P&L observations
at ~15%-of-NAV deployment:

| horizon | P(NAV < 50%) | P(NAV < 30%) |
|---|---|---|
| 1y | 20.3% | 5.9% |
| 3y | 58.8% | 32.8% |

The 'your risk is diabolical' critique quantifies as a coin-flip-scale
3-year half-loss probability on this synthetic surface at this sizing.

## §10(e) Cost / fill sensitivity

| fee multiplier | median expectancy per cycle | share positive |
|---|---|---|
| x1 | $1,072 | 100% |
| x2 | $1,014 | 100% |
| x3 | $1,045 | 100% |

Fees x1..x3 barely dent the (synthetic) top-kept expectancy — cycle P&L is
dominated by price moves, not commissions, at SPX scale. Fill-model bounds:
aggregate CONSERVATIVE fills 367 vs MID 482 in the P5 grid (bounds hold);
OPTIMISTIC is never headlined (PLAN §7.2).

## Machinery validation summary

- 154-test suite green: conservation, settlement-to-the-cent, no-lookahead
  property, Track A == Track B == sweep-runner equivalences (1e-10 on the
  10y world), IV round-trip <= 1e-6, IBKR-metric golden (Sharpe 2.99 /
  Sortino 4.45 reconstruction), regime == independent reference, all 8
  defense actions on a scripted gap week, QA gate with truth reconciliation.
- Every run is in `experiments/ledger.parquet` (worldgen/qa/sweep/p5run/
  study/match): if it isn't in the ledger, it didn't happen.

## Pass-2 preconditions

Purchase per PLAN §4.3 (see the Pass-1 handoff note), drop files under
`data/raw/`, build the vendor adapter, run `options_strategy qa`, bump
`data_version`, rerun P2 invariants, then rerun P4 -> P6 on real data.

## Addendum (2026-08-11): candles-only disclosure + percentile-family re-runs

After Pass 1 closed, the author disclosed (2026-08-10) that his entire backtest
was candles-only with NO out-of-sample results and the defense never simulated
(PLAN §1.6/§1.7). Two consequences, both delivered:

- **`reports/candle_study.md`** — his research process replicated end-to-end on
  REAL free daily candles (explicit user-approved Pass-1 exception; candles-only,
  no options simulated). Notably: his claimed WR maps to coverage q≈0.94–0.95,
  his Kelly/EV claims are internally consistent at ~30%-of-risk credits, and
  "3 bad weeks happen below the EMA" is refuted as an entry-visible rule.
- **P4–P6 v2 SYNTHETIC re-runs** (`experiments/{p4v2,p5v2,p5v2_percentile,p6v2}/`,
  summary in `experiments/p6v2/rerun_summary.md`) with the percentile-band strike
  family as the §8.1 default: 0 survivors again (WR floor binds), mystery gate
  PASS on all 18 dims, DSR 0.210 / PBO 0.505, and a structural finding —
  percentile-band strikes never price as credits on this synthetic surface, so
  the author's stated mechanism awaits real-chain credit verification in Pass 2.

The strategy's evidential base, per the author's own disclosure, is ~6 months
paper + ~4 months live. SYNTHETIC labels and Pass-2 preconditions unchanged.
