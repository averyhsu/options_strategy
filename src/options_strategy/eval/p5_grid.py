"""P5 grid (PLAN §9.2, Pass-1 form): near-miss P4 configs x defense variants
x fill models, run through the REAL Track-B engine (resting EV-gated entries,
intraday touch monitoring) on the synthetic intraday world.

Selection rule (documented; zero P4 survivors): configs that failed exactly
one §9.1 filter, restricted to require_credit=True (resting credit orders are
the author's stated mechanism; debit structures cannot rest at a credit
limit), ranked by weekly win rate, top N. Results checkpoint after every run
so jetsam kills resume cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy import ledger
from options_strategy.config import config_hash
from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import run_backtest
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.orders import FillModel
from options_strategy.strategy.defense import DefenseConfig
from options_strategy.strategy.weekly import DoubleDiagonalWeekly, WeeklyConfig
from options_strategy.sweep.space import DIM_NAMES, weekly_config

DEFENSE_VARIANTS: list[tuple[str, DefenseConfig]] = [
    ("none", DefenseConfig(trigger="none")),
    *[
        (f"{action}/immediate", DefenseConfig(trigger="touch", timing="immediate", action=action))
        for action in (
            "close_tested_side",
            "buy_back_short",
            "roll_out",
            "roll_out_away",
            "convert_vertical",
            "close_all",
            "delta_hedge",
        )
    ],
    (
        "close_tested_side/t-1",
        DefenseConfig(trigger="touch", timing="t_minus_1", action="close_tested_side"),
    ),
    (
        "buy_back_short/t-1",
        DefenseConfig(trigger="touch", timing="t_minus_1", action="buy_back_short"),
    ),
]

FILL_MODELS = (FillModel.CONSERVATIVE, FillModel.MID)


def select_configs(sweep_metrics: Path, n: int) -> list[dict]:
    df = pl.read_parquet(sweep_metrics)
    near_miss = df.filter(
        (pl.col("prune_reasons") != "")
        & (~pl.col("prune_reasons").str.contains(","))
        & (pl.col("prune_reasons") != "no_trades")
        & pl.col("require_credit")
    )
    pool = (
        near_miss
        if near_miss.height >= n
        else df.filter((pl.col("n_cycles") >= 30) & pl.col("require_credit"))
    )
    picked = pool.sort("weekly_wr", descending=True).head(n)
    return [{k: r[k] for k in DIM_NAMES} for r in picked.iter_rows(named=True)]


def _to_resting(params: dict, defense: DefenseConfig) -> WeeklyConfig:
    cfg = weekly_config(params)
    return cfg.model_copy(
        update={
            "entry": cfg.entry.model_copy(update={"execution": "resting"}),
            "defense": defense,
        }
    )


def run_p5_grid(
    world_root: str,
    sweep_metrics: str,
    out_dir: str,
    n_configs: int = 8,
    engine_cfg: EngineConfig | None = None,
) -> dict:
    engine_cfg = engine_cfg or EngineConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "grid_results.parquet"
    done: set[tuple] = set()
    rows: list[dict] = []
    if results_path.exists():
        prev = pl.read_parquet(results_path)
        rows = prev.to_dicts()
        done = {(r["config_idx"], r["defense"], r["fill_model"]) for r in rows}

    adapter = SyntheticWorldAdapter(world_root)
    configs = select_configs(Path(sweep_metrics), n_configs)
    defense_rows: list[dict] = []
    git_sha = ledger.current_git_sha()
    ledger_rows: list[ledger.LedgerRow] = []

    for ci, params in enumerate(configs):
        for dname, defense in DEFENSE_VARIANTS:
            for fm in FILL_MODELS:
                key = (ci, dname, fm.value)
                if key in done:
                    continue
                cfg = _to_resting(params, defense)
                strat = DoubleDiagonalWeekly(cfg)
                res = run_backtest(
                    adapter,
                    strat,
                    engine_cfg.model_copy(update={"fill_model": fm}),
                    initial_cash=engine_cfg.account_size,
                )
                nav = res.daily["nav"].to_numpy()
                rets = np.diff(nav) / nav[:-1] if len(nav) > 1 else np.array([])
                cummax = np.maximum.accumulate(nav)
                row = {
                    "config_idx": ci,
                    "defense": dname,
                    "fill_model": fm.value,
                    "final_nav": float(nav[-1]),
                    "total_return": float(nav[-1] / engine_cfg.account_size - 1),
                    "max_dd": float(np.max(1 - nav / cummax)),
                    "worst_day": float(rets.min()) if len(rets) else 0.0,
                    "n_fills": len(res.portfolio.fills),
                    "n_defense_events": len(strat.defense_log),
                    "n_weeks_traded": sum(1 for w in strat.week_log if w.get("traded")),
                    "fees_paid": res.portfolio.fees_paid,
                    "config_hash": config_hash(cfg),
                }
                rows.append(row)
                for ev in strat.defense_log:
                    defense_rows.append(
                        {
                            "config_idx": ci,
                            "fill_model": fm.value,
                            **{k: (str(v) if k in ("ts",) else v) for k, v in ev.items()},
                        }
                    )
                ledger_rows.append(
                    ledger.LedgerRow(
                        kind="p5run",
                        config_hash=row["config_hash"],
                        git_sha=git_sha,
                        data_version=adapter.data_version,
                        seed=0,
                        metrics={
                            "fill_model": fm.value,
                            "defense": dname,
                            "final_nav": row["final_nav"],
                            "max_dd": row["max_dd"],
                            "n_defense_events": row["n_defense_events"],
                        },
                    )
                )
                pl.DataFrame(rows).write_parquet(results_path)  # checkpoint every run

    if defense_rows:
        new_logs = pl.DataFrame(defense_rows)
        logs_path = out / "defense_week_logs.parquet"
        if logs_path.exists():
            new_logs = pl.concat([pl.read_parquet(logs_path), new_logs], how="diagonal")
        new_logs.write_parquet(logs_path)
    if ledger_rows:
        ledger.append(ledger_rows)

    df = pl.DataFrame(rows)
    (out / "p5_report.md").write_text(_report(df, configs, adapter.data_version))
    summary = {
        "n_runs": df.height,
        "n_configs": len(configs),
        "n_defense_variants": len(DEFENSE_VARIANTS),
        "data_version": adapter.data_version,
    }
    (out / "p5_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def _report(df: pl.DataFrame, configs: list[dict], data_version: str) -> str:
    lines = [
        "# P5 intraday defense grid — SYNTHETIC world",
        "",
        f"**SYNTHETIC DATA** (`{data_version}`) — Pass-1 dress rehearsal: near-miss P4",
        "configs (selection rule in eval/p5_grid.py) run through the REAL Track-B",
        "engine with resting EV-gated entries and intraday touch monitoring.",
        "Fill-model bounds reported side-by-side per PLAN §7.2 (CONSERVATIVE = lower",
        "bound; MID = central; OPTIMISTIC never headlines).",
        "",
    ]
    for ci, params in enumerate(configs):
        sub = df.filter(pl.col("config_idx") == ci)
        if sub.height == 0:
            continue
        lines += [
            f"## Config {ci}",
            "",
            "```",
            ", ".join(f"{k}={params[k]}" for k in sorted(params)),
            "```",
            "",
            "| defense | NAV (CONS) | NAV (MID) | maxDD (CONS) | maxDD (MID) "
            "| worst day (MID) | defenses | fills (C/M) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for dname in [d for d, _ in DEFENSE_VARIANTS]:
            c = sub.filter((pl.col("defense") == dname) & (pl.col("fill_model") == "conservative"))
            m = sub.filter((pl.col("defense") == dname) & (pl.col("fill_model") == "mid"))
            if c.height == 0 or m.height == 0:
                continue
            c, m = c.row(0, named=True), m.row(0, named=True)
            lines.append(
                f"| {dname} | {c['final_nav']:,.0f} | {m['final_nav']:,.0f} "
                f"| {c['max_dd']:.1%} | {m['max_dd']:.1%} | {m['worst_day']:.1%} "
                f"| {m['n_defense_events']} | {c['n_fills']}/{m['n_fills']} |"
            )
        lines.append("")
    return "\n".join(lines)
