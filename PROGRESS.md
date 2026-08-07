# PROGRESS.md — phase completion log
Append one entry per completed phase: date | phase | git tag | evidence (test run, ledger rows, report paths).

## P0 — Bootstrap, scaffold + synthetic world — 2026-08-07
- **Tag:** `phase/p0-complete`
- **Repo/CI:** public repo https://github.com/averyhsu/options_strategy, GitHub Actions (ruff + full pytest) green on `main`.
- **Tests:** 62 passed, ruff clean. Unit: config hashing, ledger row-hash determinism, XNYS sessions + era-correct expiries incl. CBOE holiday-shift cases, Black-76 (parity, bounds via hypothesis), Heston determinism/forced-gap/early-close grid, SSVI no-arb + calendar monotonicity, microstructure tick/band consistency. Integration: schema conformity, settlement==path prints exact, QA clean on pristine world, QA attributes injected defects (0 unexpected, 0 missed), QA fails on uninjected corruption, bit-identical regeneration, CLI worldgen->qa->ledger flow.
- **AC: `options_strategy qa` clean on synthetic** — world `p0-world-synthetic` (data_version `synthetic-f3356799d33d`; 10,132,272 quote rows, 124 sessions, 206 expiries, one 1-min Fri->Fri intraday week, 11,610 injected defects): verdict **CLEAN** — unexpected sanity/structure/parity = 0/0/0, missed injected = 0, all 10,792 flagged rows attributed; forwards vs truth max rel err 6.6e-6; DF err 3.7e-4 (>=7d) / 1.2e-3 (1-7d) within tiered gates. Evidence: `experiments/p0/qa_report.md`, `experiments/p0/qa_summary.json`.
- **AC: deterministic regeneration** — two independent CLI generations of the 10.1M-row world: 132 files bit-identical (sha256 tree compare), plus pytest `test_regeneration_is_bit_identical`.
- **Ledger:** `experiments/ledger.parquet` rows `worldgen-63e6733667cf`, `qa-3a7634f58912` (plus the pre-fix generator-rev-1 rows `worldgen-2fb2126fe100`, `qa-dac4ef59b458` kept as honest history).
