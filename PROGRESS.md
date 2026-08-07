# PROGRESS.md — phase completion log
Append one entry per completed phase: date | phase | git tag | evidence (test run, ledger rows, report paths).

## P0 — Bootstrap, scaffold + synthetic world — 2026-08-07
- **Tag:** `phase/p0-complete`
- **Repo/CI:** public repo https://github.com/averyhsu/options_strategy, GitHub Actions (ruff + full pytest) green on `main`.
- **Tests:** 62 passed, ruff clean. Unit: config hashing, ledger row-hash determinism, XNYS sessions + era-correct expiries incl. CBOE holiday-shift cases, Black-76 (parity, bounds via hypothesis), Heston determinism/forced-gap/early-close grid, SSVI no-arb + calendar monotonicity, microstructure tick/band consistency. Integration: schema conformity, settlement==path prints exact, QA clean on pristine world, QA attributes injected defects (0 unexpected, 0 missed), QA fails on uninjected corruption, bit-identical regeneration, CLI worldgen->qa->ledger flow.
- **AC: `options_strategy qa` clean on synthetic** — world `p0-world-synthetic` (data_version `synthetic-f3356799d33d`; 10,132,272 quote rows, 124 sessions, 206 expiries, one 1-min Fri->Fri intraday week, 11,610 injected defects): verdict **CLEAN** — unexpected sanity/structure/parity = 0/0/0, missed injected = 0, all 10,792 flagged rows attributed; forwards vs truth max rel err 6.6e-6; DF err 3.7e-4 (>=7d) / 1.2e-3 (1-7d) within tiered gates. Evidence: `experiments/p0/qa_report.md`, `experiments/p0/qa_summary.json`.
- **AC: deterministic regeneration** — two independent CLI generations of the 10.1M-row world: 132 files bit-identical (sha256 tree compare), plus pytest `test_regeneration_is_bit_identical`.
- **Ledger:** `experiments/ledger.parquet` rows `worldgen-63e6733667cf`, `qa-3a7634f58912` (plus the pre-fix generator-rev-1 rows `worldgen-2fb2126fe100`, `qa-dac4ef59b458` kept as honest history).

## P1 — Pricing & data layer — 2026-08-07
- **Tag:** `phase/p1-complete`
- **Tests:** 88 passed, ruff clean, mypy clean on `pricing/` (now in CI).
- **AC: IV round-trip <= 1e-6** — `tests/unit/test_iv.py::test_round_trip_within_1e6_across_grid`: 625-point strike/DTE/vol grid x both option types; safeguarded Newton with Corrado-Miller seeds + bisection fallback; deep-ITM via parity rotation (`test_deep_itm_rotation`); out-of-band prices refuse with NaN; true sigma recovered to 1e-4 wherever premium > $0.50.
- **AC: parity forwards ~= generator truth** — `tests/integration/test_pricing_truth.py::test_extracted_forwards_match_generator_truth` (rel err <= 2e-4, DF <= 7.5e-4 at >=7d) plus the P0-world QA evidence (max rel err 6.6e-6 over 18,641 fits).
- **AC: settlement goldens** — `tests/unit/test_settlement.py`: PM ITM short-call print 5057.31/K5000 -> 57.31 to the cent; AM SET-style put 69.75; OTM -> 0; holiday-shifted Good-Friday weekly settles under the SHIFTED date and the unshifted date refuses; PM/AM root confusion refuses to guess (PLAN §14 pitfall).
- **Also:** analytic Black-76 greeks verified against finite differences incl. calendar theta (`test_greeks.py`); NBBO-mid marking with strike-interpolated-IV model fallback and `marked_from_model` flag, null when no anchors (`test_marking.py`); `SyntheticWorldAdapter` + explicit Pass-2 vendor stub; chain mids -> IV recovers the SSVI truth surface (median err < 1e-3, `test_iv_of_sane_mids_recovers_surface_truth`); parity-fit math single-sourced in `pricing/forwards.py` (QA now imports it).

## P2 — Engine core — 2026-08-07
- **Tag:** `phase/p2-complete`
- **Tests:** 118 passed, ruff clean, mypy clean over `pricing/` + `engine/` (18 files, in CI).
- **AC invariant §11.1 (conservation)** — `check_conservation` reconciles NAV from fill/settlement records at every EOD mark inside `run_backtest`; `test_conservation_catches_cash_tampering` proves it trips on corruption; `test_invariant_1_conservation_holds_every_session` runs it across the tiny world.
- **AC invariant §11.4 (settlement)** — engine-level goldens: `test_settlement_golden_short_put` (credit 1600 - intrinsic 10,000 - fees 3.20 to the cent) + P1 unit goldens incl. holiday-shift and AM/PM refuse-to-guess.
- **AC invariant §11.5 (P&L attribution)** — `tests/unit/test_attribution.py`: delta/gamma/theta/vega Taylor explains non-gap days within max(3%, 0.10 pt); -8% gap day flagged `is_gap_day` with residual REPORTED, not excused.
- **AC invariant §11.6a** — `test_golden_6a_buy_and_hold_index_equals_index_return`: NAV == index total return to 1e-6 across every session.
- **AC invariant §11.6b** — `test_golden_6b_short_put_pnl_is_credit_minus_intrinsic_minus_fees`: immediate-order fill at mid-minus-half-spread cross, held to official settlement; final cash == initial + credit - intrinsic - $1.60 exactly; book flat after settlement.
- **AC invariant §11.7 (determinism)** — `test_invariant_7_determinism_identical_ledger_row_hash`: identical daily frames and identical ledger row hashes across reruns.
- **AC fee reproduction** — `test_base_yaml_reproduces_author_numbers`: committed `configs/base.yaml` -> $1.60/leg all-in components; 4-leg 3-lot = $19.20; x3 sensitivity multiplier = $4.80/leg.
- **Engine features landed:** signed-net-debit combo orders (uniform credit/debit rule), resting GTC combo limits with CONSERVATIVE (cross + persist full bar, reset on uncross/bad data), MID (concession x half-spread), OPTIMISTIC (mid touch) — all filling AT the limit; immediate exits at mid + k_exit x half-spread; participation-capped partial fills; quality-flag gating (no fills against flagged/one-sided legs); R_scenario (front-expiry revaluation, sticky-strike, +/-12% x vol +/-30%) / R_width / R_margin sizing with naked-short refusal; MarketView facade; held-position marks with model fallback that raises rather than invents.
