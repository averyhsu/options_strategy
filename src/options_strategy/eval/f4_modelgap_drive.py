"""F4 forensics workstream 3: model-gap bounds on the nearest-miss configs.

Top-50 soft-ranked candidates (F4 gate off) re-run through the FULL Track-B
engine on the live world with (a) the complete defense grid (vs the collapsed
{none, close-side} proxy the sweep used) and (b) a favorable-fill bound
(FillModel.OPTIMISTIC) applied to each config's best-MID defense. Measures how
much of the Sharpe/WR gap richer defense + favorable execution can close, and
whether ANY combination reaches the record's scalars without F4.

Resumable via experiments/f4_forensics/modelgap_results.parquet.

Usage:  python -m options_strategy.eval.f4_modelgap_drive [--max-seconds N]
        python -m options_strategy.eval.f4_modelgap_drive --summarize
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time

import numpy as np
import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import run_backtest
from options_strategy.engine.config import EngineConfig, FillModel
from options_strategy.eval.f4_forensics import OUT, _chunks_df
from options_strategy.eval.metrics_ibkr import fingerprints
from options_strategy.eval.mystery import LIVE_END, LIVE_START, RF_ANNUAL, _fp_from_row
from options_strategy.eval.p5_grid import DEFENSE_VARIANTS, _to_resting
from options_strategy.eval.real_match import load_targets
from options_strategy.strategy.weekly import DoubleDiagonalWeekly
from options_strategy.sweep.abc import abc_match
from options_strategy.sweep.space import DIM_NAMES

WORLD = "data/raw/theta/live_world"
TOP_N = 50
RESULTS = OUT / "modelgap_results.parquet"


def top_soft_params() -> list[dict]:
    cache_path = OUT / "modelgap_top_params.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    target, _ = load_targets()
    df = _chunks_df()
    rows = df.to_dicts()
    fps = [_fp_from_row(r) for r in rows]
    soft = abc_match(fps, target, accept_frac=0.01, dd_tol_days=10**6)
    order = np.argsort(soft.distances)[:TOP_N]
    out = [
        {k: rows[int(i)][k] for k in DIM_NAMES} | {"idx": int(rows[int(i)]["idx"])} for i in order
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out))
    return out


def live_metrics(res, sessions_all: list[dt.date]) -> dict:
    nav = res.daily["nav"].to_numpy()
    days = res.daily["session"].to_list()
    i0 = next(i for i, s in enumerate(days) if s >= LIVE_START)
    i1 = max(i for i, s in enumerate(days) if s <= LIVE_END)
    nav_live = nav[max(i0 - 1, 0) : i1 + 1]
    live_sessions = days[i0 : i1 + 1]
    fp = fingerprints(live_sessions, nav_live, RF_ANNUAL)
    return {
        "sharpe_live": float(fp.sharpe_ann),
        "mean_daily_live": float(fp.mean_daily),
        "pct_positive_live": float(fp.pct_positive),
        "max_dd_live": float(fp.max_dd),
        "dd_peak_live": str(fp.dd_peak_date),
        "dd_valley_live": str(fp.dd_valley_date),
    }


def drive(max_seconds: float | None) -> dict:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    adapter = SyntheticWorldAdapter(WORLD)
    engine = EngineConfig(account_size=1_000_000.0)
    params_list = top_soft_params()

    rows: list[dict] = []
    done: set[tuple] = set()
    if RESULTS.exists():
        prev = pl.read_parquet(RESULTS)
        rows = prev.to_dicts()
        done = {(r["idx"], r["defense"], r["fill_model"]) for r in rows}

    def one(params: dict, dname, defense, fm: FillModel) -> None:
        cfg = _to_resting({k: params[k] for k in DIM_NAMES}, defense, "eod_immediate")
        strat = DoubleDiagonalWeekly(cfg)
        res = run_backtest(
            adapter,
            strat,
            engine.model_copy(update={"fill_model": fm}),
            initial_cash=engine.account_size,
        )
        m = live_metrics(res, [])
        rows.append(
            {
                "idx": params["idx"],
                "defense": dname,
                "fill_model": fm.value,
                **m,
                "n_weeks_traded": sum(1 for w in strat.week_log if w.get("traded")),
            }
        )
        pl.DataFrame(rows).write_parquet(RESULTS)

    exhausted = False
    # pass 1: full defense grid at MID
    for params in params_list:
        for dname, defense in DEFENSE_VARIANTS:
            key = (params["idx"], dname, FillModel.MID.value)
            if key in done:
                continue
            if max_seconds is not None and time.time() - t0 > max_seconds:
                exhausted = True
                break
            one(params, dname, defense, FillModel.MID)
        if exhausted:
            break
    # pass 2: OPTIMISTIC at each config's best-MID defense
    if not exhausted:
        df = pl.read_parquet(RESULTS)
        mid = df.filter(pl.col("fill_model") == FillModel.MID.value)
        for params in params_list:
            sub = mid.filter(pl.col("idx") == params["idx"])
            if sub.is_empty():
                continue
            best_def = sub.sort("sharpe_live", descending=True)["defense"][0]
            key = (params["idx"], best_def, FillModel.OPTIMISTIC.value)
            if key in done:
                continue
            if max_seconds is not None and time.time() - t0 > max_seconds:
                exhausted = True
                break
            defense = next(d for n, d in DEFENSE_VARIANTS if n == best_def)
            one(params, best_def, defense, FillModel.OPTIMISTIC)

    total = len(params_list) * len(DEFENSE_VARIANTS) + len(params_list)
    return {"done": len(rows), "total": total, "complete": len(rows) >= total}


def summarize() -> dict:
    df = pl.read_parquet(RESULTS)
    base = df.filter((pl.col("defense") == "none") & (pl.col("fill_model") == "mid"))
    best = df.sort("sharpe_live", descending=True).head(10)
    hit = df.filter((pl.col("sharpe_live") >= 2.99) & (pl.col("pct_positive_live") >= 0.7241))
    jul = df.filter(
        (pl.col("dd_peak_live") >= "2026-07-08") & (pl.col("dd_peak_live") <= "2026-07-12")
    )
    out = {
        "n_runs": df.height,
        "base_median_sharpe": float(base["sharpe_live"].median()) if base.height else None,
        "best_sharpe": float(df["sharpe_live"].max()),
        "best_rows": best.select(
            "idx",
            "defense",
            "fill_model",
            "sharpe_live",
            "pct_positive_live",
            "max_dd_live",
            "dd_peak_live",
            "n_weeks_traded",
        ).to_dicts(),
        "n_reaching_record_scalars": hit.height,
        "n_dd_peak_in_f4_window": jul.height,
    }
    (OUT / "modelgap_summary.json").write_text(json.dumps(out, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    if args.summarize:
        print(json.dumps(summarize(), indent=2))
        return 0
    print(json.dumps(drive(args.max_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
