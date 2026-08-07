"""Regime study on SYNTHETIC candles (PLAN §8.3 deliverable, Pass-1 form).

Replicates the author's claim structurally — "3-losing-week clusters happen
below the 21EMA" — against a scripted synthetic world. Every output is labeled
SYNTHETIC: this validates the MACHINERY (weekly aggregation, EMA/ATR, event
tagging, streak analysis), not any real-market claim. The real 1999->present
candle replication runs in Pass 2 when real data arrives (ASSUMPTIONS.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.strategy.regime import RegimeConfig, regime_frame


def run_regime_study(world_root: str | Path, cfg: RegimeConfig, out_md: str | Path) -> dict:
    adapter = SyntheticWorldAdapter(world_root)
    daily = (
        adapter.underlying_bars()
        .with_columns(session=pl.col("ts").dt.date())
        .group_by("session", maintain_order=True)
        .agg(
            open=pl.col("open").first(),
            high=pl.col("high").max(),
            low=pl.col("low").min(),
            close=pl.col("close").last(),
        )
    )
    wk = regime_frame(daily, cfg).filter(pl.col("state") != "warmup")
    wk = wk.with_columns(ret=pl.col("close").pct_change()).drop_nulls("ret")
    wk = wk.with_columns(
        losing=pl.col("ret") < 0,
        state_prev=pl.col("state").shift(1),
    ).drop_nulls("state_prev")

    # losing streaks and the state they started under
    streaks: list[dict] = []
    run = 0
    start_state = None
    for row in wk.iter_rows(named=True):
        if row["losing"]:
            if run == 0:
                start_state = row["state_prev"]
            run += 1
        else:
            if run >= 2:
                streaks.append({"length": run, "start_state": start_state})
            run = 0
    if run >= 2:
        streaks.append({"length": run, "start_state": start_state})

    by_state = (
        wk.group_by("state")
        .agg(
            n=pl.len(),
            mean_ret=pl.col("ret").mean(),
            win_rate=(pl.col("ret") > 0).mean(),
            worst=pl.col("ret").min(),
        )
        .sort("state")
    )
    by_event = (
        wk.group_by("event")
        .agg(n=pl.len(), mean_next_ret=pl.col("ret").shift(-1).mean())
        .sort("event")
    )
    long_streaks = [s for s in streaks if s["length"] >= 3]
    bear_started = sum(1 for s in long_streaks if s["start_state"] == "bear")

    stats = {
        "label": "SYNTHETIC",
        "n_weeks": wk.height,
        "ema_len": cfg.ema_len,
        "by_state": by_state.to_dicts(),
        "by_event": by_event.to_dicts(),
        "n_losing_streaks_ge2": len(streaks),
        "n_losing_streaks_ge3": len(long_streaks),
        "ge3_started_in_bear": bear_started,
        "ge3_started_in_bull": len(long_streaks) - bear_started,
    }

    lines = [
        "# Regime study — SYNTHETIC world",
        "",
        "**SYNTHETIC DATA.** This study runs the 21-EMA weekly regime machinery on a",
        "scripted synthetic world to validate the pipeline (PLAN §8.3). It supports",
        "no real-market conclusion; the 1999->present replication happens in Pass 2.",
        "",
        f"- world: `{adapter.manifest['name']}` (data_version `{adapter.data_version}`)",
        f"- weeks analyzed: {stats['n_weeks']} | ema_len {cfg.ema_len}",
        "",
        "## Weekly returns by regime state",
        "",
        "| state | n | mean ret | win rate | worst |",
        "|---|---|---|---|---|",
    ]
    for r in stats["by_state"]:
        lines.append(
            f"| {r['state']} | {r['n']} | {r['mean_ret']:.4%} | {r['win_rate']:.1%} "
            f"| {r['worst']:.2%} |"
        )
    lines += [
        "",
        "## Events",
        "",
        "| event | n | mean next-week ret |",
        "|---|---|---|",
    ]
    for r in stats["by_event"]:
        nxt = r["mean_next_ret"]
        lines.append(
            f"| {r['event']} | {r['n']} | {('%.4f%%' % (100 * nxt)) if nxt is not None else '-'} |"
        )
    lines += [
        "",
        "## Losing-week clusters (the author's claim, synthetic rehearsal)",
        "",
        f"- streaks >= 2: {stats['n_losing_streaks_ge2']}; "
        f"streaks >= 3: {stats['n_losing_streaks_ge3']}",
        f"- of the >=3 streaks, started while state was BEAR: {stats['ge3_started_in_bear']}, "
        f"BULL: {stats['ge3_started_in_bull']}",
        "",
    ]
    out = Path(out_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    (out.with_suffix(".json")).write_text(json.dumps(stats, indent=2, default=str))
    return stats
