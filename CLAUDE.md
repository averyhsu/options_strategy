# options_strategy

Research-grade backtester + parameter-identification system for a weekly SPX double-diagonal options strategy family. **Research software only — no live trading, no order routing, no broker credentials. Not investment advice.**

## Source of truth
- **`PLAN.md`** — scope, architecture, parameter spaces, phases P0–P7, acceptance criteria, and the autonomous loop protocol (§12.0). Read it in full at kickoff; re-read the current phase's section each time the loop re-enters ENGINEER. If this file and PLAN.md ever conflict, PLAN.md wins — flag the conflict instead of resolving it silently.
- **`ASSUMPTIONS.md`** — every nontrivial modeling choice plus the autonomous-mode defaults (one line each: date, choice, alternative considered, why).
- **`PROGRESS.md`** — one entry per completed phase: date, phase, tag, evidence (test run, ledger rows, report paths).
- **`experiments/ledger.parquet`** — every run: run_id, config_hash, git_sha, data_version, seed, metrics. If it isn't in the ledger, it didn't happen.

## Execution mode: AUTONOMOUS LOOP (PLAN.md §12.0)
Phases run strictly in order, continuously, with no human gate between them:

**ENGINEER → GENERATE → VALIDATE → TEST** — repeat until every acceptance criterion of the current phase is machine-verifiably green, then: commit, tag `phase/pN-complete`, push, log evidence in PROGRESS.md, and advance. Continue until P6 completes (Pass 1, fully synthetic), then stop and report.

- Never weaken a test, tolerance, or acceptance criterion to advance. An honest stall beats a dishonest green.
- **Stall rule:** 5 consecutive iterations failing the same criterion without measurable progress ⇒ stop, write `STALL_REPORT.md`, await the user.
- Only three reasons to interrupt the loop: a stall, a genuine external blocker (missing data, unauthenticated tooling), or completion. Everything else proceeds on the documented defaults in ASSUMPTIONS.md.

## Git & GitHub
- Commit at every green TEST beat (small, descriptive messages). Push at minimum at every phase boundary. Tag phases `phase/p0-complete`, `phase/p1-complete`, …
- GitHub Actions CI (ruff + full pytest) is part of P0 and must stay green on `main`.
- **The repo is PUBLIC.** Never commit raw/vendor market data (`data/raw/`, `data/vendor/` are gitignored) — purchased data is licensed and committing it to a public repo is redistribution. If licensed data ever enters git history: stall-stop BEFORE any further push and report; a history rewrite is required. Synthetic generator code + seeds, configs, reports, and the ledger ARE committed.

## Commands
```bash
# env manager: miniconda env `options_strategy` (user directive 2026-08-06 — replaces uv)
conda run -n options_strategy pip install -e ".[dev]"    # environment (python 3.12)
conda run -n options_strategy pytest -n auto             # full test suite (the TEST beat; must be green)
conda run -n options_strategy ruff check . --fix         # lint
conda run -n options_strategy options_strategy qa        # data QA gate — run before ANY new dataset is used
conda run -n options_strategy options_strategy run --config configs/experiments/<name>.yaml
conda run -n options_strategy options_strategy sweep --space configs/spaces/<name>.yaml
conda run -n options_strategy options_strategy match --targets configs/fingerprints.yaml
conda run -n options_strategy options_strategy report --run <run_id>
```

## Non-negotiable rules
- **Scope guard:** weekly SPX double diagonals only. No 0DTE, no futures, no other underlyings. Do not reintroduce them "helpfully."
- **Correctness before speed.** An honest "no edge" or "not identifiable" result is a success.
- Never silently change metric definitions, fingerprint targets, or acceptance criteria (PLAN.md §2, §12). If one seems wrong, stall-stop and explain.
- Invariants in PLAN.md §11 (cash conservation, no-lookahead, parity gate, settlement goldens, determinism, Track A ≡ Track B) run in CI and must stay green. Never loosen a tolerance to make a test pass.
- Experiments run from YAML configs, never edited constants. Same config + seed + data_version ⇒ bit-identical results.
- No fabricated or from-memory market data. Synthetic data is labeled SYNTHETIC everywhere, including plots and report titles.
- New real data: `options_strategy qa` first, commit the QA report, bump `data_version`, rerun P2 invariants — only then strategy runs.
- Strategy code accesses market data only through the `MarketView(t)` facade (no raw loader imports).
- Reports always show deflated metrics (DSR, PBO) alongside raw ones.

## Conventions
- Python 3.12 in the `options_strategy` miniconda env (user directive 2026-08-06 — replaces uv), polars-first, numba only after a profile shows need. Ruff + pytest + hypothesis; mypy on `pricing/` and `engine/`.
- All timestamps ET, tz-aware, XCBOE calendar. SPXW = PM-settled, SPX monthlies = AM-settled (SET) — never mix (PLAN.md §14 pitfalls).
- Prefer boring, explicit code over clever broadcasting.
- **Autonomous defaults** (pre-seeded in ASSUMPTIONS.md; surface them in every report): Pass 1 uses synthetic data only; account size $100,000 for fee granularity; rf = synthetic rates curve in Pass 1, 3M T-bill in Pass 2; vendor adapters are built only when real data actually arrives. Stall-stop and ask only for genuine blockers.
