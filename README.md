# options_strategy

Research-grade backtesting and parameter-identification system for a family of weekly **SPX double-diagonal** option strategies, reverse-engineered from a public trader's disclosures — built to evaluate the family's robustness honestly (walk-forward, deflated Sharpe ratio, probability of backtest overfitting, stress tests, risk-of-ruin).

> **Research software only.** No live trading, no order routing, no broker integration, and no live-trading pathway will ever be added. Nothing in this repository is investment advice. A configuration that matches published performance fingerprints is not evidence of the original trader's true rules, nor of future profitability. An honest "no edge after costs" or "not identifiable" result is a successful outcome here.

## Orientation

- [`PLAN.md`](PLAN.md) — the full project spec: mission, architecture, parameter spaces, phases P0–P7 with acceptance criteria, and the autonomous loop protocol (§12.0).
- [`CLAUDE.md`](CLAUDE.md) — working agreements for the Claude Code sessions building this.
- [`ASSUMPTIONS.md`](ASSUMPTIONS.md) — append-only log of every nontrivial modeling assumption.
- [`PROGRESS.md`](PROGRESS.md) — phase completion log with machine-verifiable evidence.

## Data policy

This repository is **public** and contains **no market data**. Purchased/licensed historical data (`data/raw/`, `data/vendor/`) is permanently gitignored — committing it would be public redistribution of licensed data. All committed datasets, fixtures, and report inputs are produced by the seeded synthetic world generator and are labeled **SYNTHETIC** everywhere they appear, including plots and report titles. Pass 1 of the project (phases P0–P6) runs entirely on synthetic data.

## Environment

```bash
conda create -y -n options_strategy python=3.12
conda run -n options_strategy pip install -e ".[dev]"
conda run -n options_strategy pytest -n auto
```

CI runs the same lint + test suite on plain `pip` (GitHub Actions, `.github/workflows/ci.yml`).
