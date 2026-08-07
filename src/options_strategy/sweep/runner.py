"""Coarse-sweep orchestration (PLAN §9.1): Sobol configs -> fast Track-A runs
-> prune -> marginals report -> ledger rows for EVERY evaluated config.
"""

from __future__ import annotations

import json
import time
from itertools import pairwise
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy import ledger
from options_strategy.config import config_hash
from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.config import EngineConfig
from options_strategy.sweep.fast_runner import SweepResult, run_config
from options_strategy.sweep.precompute import build_cache
from options_strategy.sweep.space import (
    DIM_NAMES,
    EMA_LENS,
    HYSTERESIS,
    SweepRunConfig,
    sobol_params,
    weekly_config,
)

PRUNE_MIN_CYCLES = 30
PRUNE_WR_LO, PRUNE_WR_HI = 0.75, 0.97
PRUNE_WIN_MAG_LO, PRUNE_WIN_MAG_HI = 0.15, 0.45
PRUNE_MAX_DD = 0.40
KEEP_RANDOM_FRAC = 0.02


def metrics_from_result(res: SweepResult, initial_cash: float) -> dict:
    nav = res.nav_daily
    rets = np.diff(nav) / nav[:-1]
    cummax = np.maximum.accumulate(nav)
    max_dd = float(np.max(1.0 - nav / cummax)) if len(nav) else 0.0
    pnls = np.array([c["pnl_dollars"] for c in res.cycles])
    deployed = np.array([c["r_dollars"] * c["qty"] for c in res.cycles])
    wins = pnls > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        mag = np.where(deployed > 0, pnls / deployed, np.nan)
    win_mag = mag[wins & np.isfinite(mag)]
    loss_mag = mag[~wins & np.isfinite(mag)]
    std = float(np.std(rets, ddof=1)) if len(rets) > 2 else 0.0
    return {
        "n_cycles": len(pnls),
        "n_fills": res.n_fills,
        "fees_paid": float(res.fees_paid),
        "expectancy_per_cycle": float(pnls.mean()) if len(pnls) else 0.0,
        "weekly_wr": float(wins.mean()) if len(pnls) else 0.0,
        "win_mag_median": float(np.median(win_mag)) if len(win_mag) else float("nan"),
        "loss_mag_median": float(np.median(loss_mag)) if len(loss_mag) else float("nan"),
        "max_dd": max_dd,
        "total_return": float(nav[-1] / initial_cash - 1.0),
        "ann_sharpe_raw": float(np.mean(rets) / std * np.sqrt(252)) if std > 0 else 0.0,
        "final_nav": float(nav[-1]),
    }


def prune_reasons(m: dict) -> list[str]:
    reasons = []
    if m["n_cycles"] < PRUNE_MIN_CYCLES:
        return ["no_trades"]
    if m["expectancy_per_cycle"] <= 0:
        reasons.append("expectancy")
    if not (PRUNE_WR_LO <= m["weekly_wr"] <= PRUNE_WR_HI):
        reasons.append("win_rate")
    if not (
        np.isfinite(m["win_mag_median"])
        and PRUNE_WIN_MAG_LO <= m["win_mag_median"] <= PRUNE_WIN_MAG_HI
    ):
        reasons.append("win_magnitude")
    if m["max_dd"] > PRUNE_MAX_DD:
        reasons.append("drawdown")
    return reasons


CHUNK_SIZE = 2048


def run_chunk(
    run_cfg: SweepRunConfig,
    start: int,
    size: int = CHUNK_SIZE,
    engine_cfg: EngineConfig | None = None,
) -> Path:
    """Evaluate configs [start, start+size) and checkpoint them to parquet.

    Idempotent: an existing checkpoint is returned untouched, so a killed run
    (this 8GB box jetsams long-lived processes under memory pressure) resumes
    by re-invoking the same chunks. Each chunk is meant to run in its OWN
    short-lived process.
    """
    engine_cfg = engine_cfg or EngineConfig()
    ckpt_dir = Path(run_cfg.out_dir) / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt = ckpt_dir / f"chunk_{start:06d}.parquet"
    if ckpt.exists():
        return ckpt

    adapter = SyntheticWorldAdapter(run_cfg.world)
    combos = [(e, h) for e in EMA_LENS for h in HYSTERESIS]
    cache = build_cache(adapter, combos)

    params_list = sobol_params(run_cfg.n_configs, run_cfg.seed)[start : start + size]
    rows: list[dict] = []
    t0 = time.time()
    for offset, params in enumerate(params_list):
        cfg = weekly_config(params)
        res = run_config(
            cache,
            cfg,
            engine_cfg.account_size,
            engine_cfg.fees.per_contract_leg,
            engine_cfg.participation_cap,
        )
        m = metrics_from_result(res, engine_cfg.account_size)
        rows.append(
            {
                "idx": start + offset,
                **params,
                **m,
                "prune_reasons": ",".join(prune_reasons(m)),
                "config_hash": config_hash(cfg),
            }
        )
    pl.DataFrame(rows).write_parquet(ckpt)
    print(f"chunk {start}: {len(rows)} configs in {time.time() - t0:.0f}s -> {ckpt.name}")
    return ckpt


def finalize(run_cfg: SweepRunConfig) -> dict:
    """Assemble checkpoints, prune, report, and ledger every config."""
    out_dir = Path(run_cfg.out_dir)
    ckpts = sorted((out_dir / "checkpoints").glob("chunk_*.parquet"))
    df = pl.concat([pl.read_parquet(p) for p in ckpts]).sort("idx")
    if df.height != run_cfg.n_configs:
        raise RuntimeError(f"checkpoints cover {df.height} configs, expected {run_cfg.n_configs}")

    adapter = SyntheticWorldAdapter(run_cfg.world)
    rng = np.random.default_rng(run_cfg.seed)
    survived = df["prune_reasons"] == ""
    random_keep = pl.Series((rng.random(df.height) < KEEP_RANDOM_FRAC) & (~survived.to_numpy()))
    df = df.with_columns(survived=survived, kept=survived | random_keep)
    df.write_parquet(out_dir / "sweep_metrics.parquet")
    df.filter(pl.col("kept")).write_parquet(out_dir / "survivors.parquet")

    git_sha = ledger.current_git_sha()
    ledger_rows = [
        ledger.LedgerRow(
            kind="sweep",
            config_hash=r["config_hash"],
            git_sha=git_sha,
            data_version=adapter.data_version,
            seed=run_cfg.seed,
            metrics={
                "n_cycles": r["n_cycles"],
                "expectancy_per_cycle": r["expectancy_per_cycle"],
                "weekly_wr": r["weekly_wr"],
                "max_dd": r["max_dd"],
                "final_nav": r["final_nav"],
            },
            artifacts=[],
        )
        for r in df.iter_rows(named=True)
    ]
    ledger.append(ledger_rows)

    summary = {
        "n_configs": df.height,
        "n_survivors": int(df["survived"].sum()),
        "n_kept": int(df["kept"].sum()),
        "data_version": adapter.data_version,
    }
    (out_dir / "pruning_report.md").write_text(_report(df, summary, run_cfg))
    (out_dir / "sweep_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def run_sweep(run_cfg: SweepRunConfig, engine_cfg: EngineConfig | None = None) -> dict:
    """Single-process convenience path (tests, small runs): chunks then finalize."""
    for start in range(0, run_cfg.n_configs, CHUNK_SIZE):
        run_chunk(run_cfg, start, min(CHUNK_SIZE, run_cfg.n_configs - start), engine_cfg)
    return finalize(run_cfg)


def _marginal(df: pl.DataFrame, name: str) -> list[tuple[str, int, float]]:
    col = df[name]
    if col.dtype in (pl.Float64, pl.Float32) and col.n_unique() > 12:
        edges = np.linspace(float(col.min()), float(col.max()) + 1e-9, 9)
        out = []
        vals = col.to_numpy()
        surv = df["survived"].to_numpy()
        for lo, hi in pairwise(edges):
            mask = (vals >= lo) & (vals < hi)
            if mask.sum() == 0:
                continue
            out.append((f"[{lo:.3g},{hi:.3g})", int(mask.sum()), float(surv[mask].mean())))
        return out
    grouped = df.group_by(name).agg(n=pl.len(), surv=pl.col("survived").mean()).sort(name)
    return [(str(r[0]), int(r[1]), float(r[2])) for r in grouped.iter_rows()]


def _report(df: pl.DataFrame, summary: dict, run_cfg: SweepRunConfig) -> str:
    reason_counts: dict[str, int] = {}
    for reasons in df["prune_reasons"]:
        for r in reasons.split(",") if reasons else []:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    surv = df.filter(pl.col("survived"))
    lines = [
        "# P4 coarse-sweep pruning report — SYNTHETIC world",
        "",
        "**SYNTHETIC DATA** — Pass-1 dress rehearsal on the scripted 10y world "
        f"(`{summary['data_version']}`). No real-market conclusion is implied.",
        "",
        f"- configs evaluated: {summary['n_configs']:,} (Sobol, seed {run_cfg.seed})",
        f"- survivors: {summary['n_survivors']:,} "
        f"({summary['n_survivors'] / summary['n_configs']:.1%})",
        f"- kept (survivors + {KEEP_RANDOM_FRAC:.0%} random bias-guard): {summary['n_kept']:,}",
        "",
        "## Prune reasons (a config can hit several)",
        "",
        "| reason | n |",
        "|---|---|",
    ]
    for r, n in sorted(reason_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {r} | {n:,} |")
    if surv.height:
        lines += [
            "",
            "## Survivor metrics",
            "",
            "| metric | p10 | median | p90 |",
            "|---|---|---|---|",
        ]
        for met in (
            "expectancy_per_cycle",
            "weekly_wr",
            "win_mag_median",
            "max_dd",
            "ann_sharpe_raw",
            "total_return",
        ):
            v = surv[met].drop_nans().drop_nulls()
            if v.len():
                lines.append(
                    f"| {met} | {v.quantile(0.1):.4g} | {v.median():.4g} | {v.quantile(0.9):.4g} |"
                )
    lines += ["", "## Parameter marginals (survival rate by bin)", ""]
    for name in DIM_NAMES:
        lines += [f"### {name}", "", "| bin | n | survival |", "|---|---|---|"]
        for label, n, rate in _marginal(df, name):
            lines.append(f"| {label} | {n:,} | {rate:.1%} |")
        lines.append("")
    return "\n".join(lines)
