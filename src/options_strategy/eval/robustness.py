"""Robustness battery (PLAN §10, Pass-1 synthetic scale): walk-forward,
deflated Sharpe, PBO via CSCV, stress book + weekend-gap injector, block-
bootstrap risk-of-ruin, and fee sensitivity — all over the kept P4 set on the
10y synthetic world via the equivalence-anchored fast runner.
"""

from __future__ import annotations

import datetime as dt
from itertools import combinations
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import norm

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.config import EngineConfig
from options_strategy.sweep.fast_runner import run_config
from options_strategy.sweep.precompute import build_cache
from options_strategy.sweep.space import DIM_NAMES, EMA_LENS, HYSTERESIS, weekly_config

TRADING_DAYS = 252.0


def kept_nav_matrix(world_root: str, survivors_path: str, out_dir: str) -> Path:
    """Daily NAV per kept config (checkpointed once)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / "kept_navs.parquet"
    if ckpt.exists():
        return ckpt
    adapter = SyntheticWorldAdapter(world_root)
    combos = [(e, h) for e in EMA_LENS for h in HYSTERESIS]
    cache = build_cache(adapter, combos)
    engine = EngineConfig()
    kept = pl.read_parquet(survivors_path)
    rows = {}
    cycles_rows = []
    for r in kept.iter_rows(named=True):
        params = {k: r[k] for k in DIM_NAMES}
        res = run_config(
            cache,
            weekly_config(params),
            engine.account_size,
            engine.fees.per_contract_leg,
            engine.participation_cap,
        )
        rows[str(r["idx"])] = res.nav_daily.tolist()
        for c in res.cycles:
            cycles_rows.append(
                {
                    "idx": r["idx"],
                    "entry_session": c["entry_session"],
                    "pnl": c["pnl_dollars"],
                    "deployed": c["r_dollars"] * c["qty"],
                    "nav_before": c["nav_before"],
                }
            )
    frame = pl.DataFrame({"session": [s.isoformat() for s in cache.sessions], **rows})
    frame.write_parquet(ckpt)
    pl.DataFrame(cycles_rows).write_parquet(out / "kept_cycles.parquet")
    return ckpt


def walk_forward(
    navs: pl.DataFrame, train_years: int = 3, test_months: int = 6, step_months: int = 3
) -> dict:
    sessions = [dt.date.fromisoformat(s) for s in navs["session"].to_list()]
    ids = [c for c in navs.columns if c != "session"]
    mat = np.column_stack([navs[c].to_numpy() for c in ids])  # (T, N)
    rets = np.diff(mat, axis=0) / mat[:-1]
    folds = []
    t0 = sessions[0]
    k = 0
    while True:
        train_end = _add_months(t0, 12 * train_years + step_months * k)
        test_end = _add_months(train_end, test_months)
        if test_end > sessions[-1]:
            break
        i_tr = _idx_before(sessions, train_end)
        i_te = _idx_before(sessions, test_end)
        if i_te <= i_tr + 5:
            break
        for anchored in (True, False):
            i_start = (
                0 if anchored else _idx_before(sessions, _add_months(train_end, -12 * train_years))
            )
            tr = rets[i_start:i_tr].mean(axis=0)
            top = np.argsort(tr)[-max(len(ids) // 10, 1) :]
            te = rets[i_tr:i_te][:, top].mean(axis=0)
            folds.append(
                {
                    "mode": "anchored" if anchored else "rolling",
                    "train_end": train_end.isoformat(),
                    "n_selected": len(top),
                    "oos_mean_daily_ret": float(te.mean()),
                    "oos_share_profitable": float((te > 0).mean()),
                }
            )
        k += 1
    share_ok = [f["oos_share_profitable"] for f in folds]
    return {
        "folds": folds,
        "n_folds": len(folds),
        "median_oos_share_profitable": float(np.median(share_ok)) if folds else float("nan"),
    }


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod((d.year * 12 + d.month - 1) + months, 12)
    return dt.date(y, m + 1, min(d.day, 28))


def _idx_before(sessions: list[dt.date], cutoff: dt.date) -> int:
    return int(np.searchsorted(np.array(sessions, dtype="datetime64[D]"), np.datetime64(cutoff)))


def deflated_sharpe(navs: pl.DataFrame, n_trials: int) -> dict:
    ids = [c for c in navs.columns if c != "session"]
    mat = np.column_stack([navs[c].to_numpy() for c in ids])
    rets = np.diff(mat, axis=0) / mat[:-1]
    srs = rets.mean(axis=0) / np.where(
        rets.std(axis=0, ddof=1) > 0, rets.std(axis=0, ddof=1), np.inf
    )
    best = int(np.argmax(srs))
    r = rets[:, best]
    t_n = len(r)
    sr = float(srs[best])  # daily SR
    g3 = float(((r - r.mean()) ** 3).mean() / r.std(ddof=0) ** 3)
    g4 = float(((r - r.mean()) ** 4).mean() / r.std(ddof=0) ** 4)
    var_sr = float(np.var(srs, ddof=1)) if len(srs) > 2 else (1.0 / t_n)
    emc = 0.5772156649
    sr0 = np.sqrt(var_sr) * (
        (1 - emc) * norm.ppf(1 - 1.0 / n_trials) + emc * norm.ppf(1 - 1.0 / (n_trials * np.e))
    )
    denom = np.sqrt(max(1 - g3 * sr + (g4 - 1) / 4.0 * sr**2, 1e-12))
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(t_n - 1) / denom))
    return {
        "best_idx": ids[best],
        "sharpe_ann_best": sr * np.sqrt(TRADING_DAYS),
        "sr0_daily_expected_max": float(sr0),
        "n_trials": n_trials,
        "dsr": dsr,
    }


def pbo_cscv(navs: pl.DataFrame, n_blocks: int = 16, n_splits: int = 200, seed: int = 7) -> dict:
    ids = [c for c in navs.columns if c != "session"]
    mat = np.column_stack([navs[c].to_numpy() for c in ids])
    rets = np.diff(mat, axis=0) / mat[:-1]
    t_n = rets.shape[0] - (rets.shape[0] % n_blocks)
    blocks = rets[:t_n].reshape(n_blocks, t_n // n_blocks, len(ids))

    def block_sharpe(b: np.ndarray) -> np.ndarray:
        mu = b.mean(axis=0)
        sd = b.std(axis=0, ddof=1)
        return np.where(sd > 0, mu / sd, 0.0)

    all_combos = list(combinations(range(n_blocks), n_blocks // 2))
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(all_combos), size=min(n_splits, len(all_combos)), replace=False)
    lambdas = []
    for pi in picks:
        train_ids = set(all_combos[pi])
        tr = np.concatenate([blocks[i] for i in range(n_blocks) if i in train_ids])
        te = np.concatenate([blocks[i] for i in range(n_blocks) if i not in train_ids])
        best = int(np.argmax(block_sharpe(tr)))
        te_sr = block_sharpe(te)
        rank = float((te_sr < te_sr[best]).mean() + 0.5 * (te_sr == te_sr[best]).mean())
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        lambdas.append(np.log(rank / (1 - rank)))
    lambdas = np.array(lambdas)
    return {
        "n_splits": len(lambdas),
        "pbo": float((lambdas <= 0).mean()),
        "lambda_median": float(np.median(lambdas)),
    }


def stress_windows(
    navs: pl.DataFrame, windows: list[tuple[str, dt.date, dt.date]], top_k: int = 5
) -> list[dict]:
    sessions = [dt.date.fromisoformat(s) for s in navs["session"].to_list()]
    ids = [c for c in navs.columns if c != "session"]
    mat = np.column_stack([navs[c].to_numpy() for c in ids])
    total = mat[-1] / mat[0]
    top = np.argsort(total)[-top_k:]
    out = []
    for name, a, b in windows:
        i0, i1 = _idx_before(sessions, a), _idx_before(sessions, b)
        if i1 <= i0:
            continue
        impact = mat[i1, top] / mat[i0, top] - 1.0
        out.append(
            {
                "window": name,
                "start": a.isoformat(),
                "end": b.isoformat(),
                "median_impact": float(np.median(impact)),
                "worst_impact": float(impact.min()),
            }
        )
    return out


def risk_of_ruin(cycles_path: str, n_paths: int = 10_000, block: int = 4, seed: int = 11) -> dict:
    cy = pl.read_parquet(cycles_path)
    # weekly pnl as a fraction of then-current NAV, pooled over kept configs
    frac = (cy["pnl"] / cy["nav_before"]).drop_nulls().to_numpy()
    frac = frac[np.isfinite(frac)]
    rng = np.random.default_rng(seed)
    out = {}
    for label, weeks in (("1y", 52), ("3y", 156)):
        n_blocks = int(np.ceil(weeks / block))
        starts = rng.integers(0, max(len(frac) - block, 1), size=(n_paths, n_blocks))
        path_rets = np.empty((n_paths, n_blocks * block))
        for j in range(n_blocks):
            for b in range(block):
                path_rets[:, j * block + b] = frac[starts[:, j] + b]
        path_rets = path_rets[:, :weeks]
        nav_paths = np.cumprod(1.0 + path_rets, axis=1)
        run_min = np.minimum.accumulate(nav_paths, axis=1)[:, -1]
        out[label] = {
            "p_below_50pct": float((run_min < 0.5).mean()),
            "p_below_30pct": float((run_min < 0.3).mean()),
        }
    out["n_weekly_obs"] = len(frac)
    return out


def fee_sensitivity(
    world_root: str, survivors_path: str, top_k: int = 10, multipliers: tuple = (1.0, 2.0, 3.0)
) -> list[dict]:
    adapter = SyntheticWorldAdapter(world_root)
    kept = pl.read_parquet(survivors_path).sort("expectancy_per_cycle", descending=True).head(top_k)
    params_list = [{k: r[k] for k in DIM_NAMES} for r in kept.iter_rows(named=True)]
    combos = sorted({(p["ema_len"], p["hysteresis"]) for p in params_list})
    cache = build_cache(adapter, combos)
    engine = EngineConfig()
    out = []
    for mult in multipliers:
        exps = []
        for params in params_list:
            res = run_config(
                cache,
                weekly_config(params),
                engine.account_size,
                engine.fees.per_contract_leg * mult,
                engine.participation_cap,
            )
            pnls = np.array([c["pnl_dollars"] for c in res.cycles])
            exps.append(float(pnls.mean()) if len(pnls) else 0.0)
        out.append(
            {
                "fee_multiplier": mult,
                "median_expectancy_per_cycle": float(np.median(exps)),
                "share_positive": float(np.mean([e > 0 for e in exps])),
            }
        )
    return out


def scripted_stress_windows_from_config(
    world_cfg_sessions: list[dt.date],
) -> list[tuple[str, dt.date, dt.date]]:
    """The P4 world's scripted segments, mapped to dates (see the world yaml)."""
    s = world_cfg_sessions
    seg_bounds = [500, 560, 1000, 1055, 1455, 1835, 2255, 2280]
    names = [
        "SCRIPTED-VOL-EVENT-1",
        "recovery-1",
        "SCRIPTED-CRASH",
        "recovery-2",
        "SCRIPTED-BEAR-GRIND",
        "recovery-3",
        "SCRIPTED-VIX-SPIKE",
    ]
    out = []
    prev = seg_bounds[0]
    for name, b in zip(names, seg_bounds[1:], strict=True):
        if prev < len(s) and b <= len(s) and name.startswith("SCRIPTED"):
            out.append((name, s[prev], s[min(b, len(s) - 1)]))
        prev = b
    return out
