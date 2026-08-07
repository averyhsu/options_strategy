"""ABC fingerprint matcher (PLAN §9.3).

Summary vector per candidate: {ann Sharpe, ann Sortino, sigma_daily, downside
dev, mean daily, %pos days, maxDD, recovery days, weekly WR, median win %R,
log-VAMI curve L2}. Distance = weighted normalized L2 (feature scales = robust
MAD across the candidate population); the DD peak->valley DATE match is a HARD
constraint (+/- tol days). Accept rho < eps with eps set by the target
acceptance fraction; the posterior IS the accepted set — no argmax is ever
crowned (PLAN §9.4).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from options_strategy.eval.metrics_ibkr import Fingerprints

SCALAR_FEATURES = (
    "sharpe_ann",
    "sortino_ann",
    "std_daily",
    "downside_dev_daily",
    "mean_daily",
    "pct_positive",
    "max_dd",
    "recovery_days",
    "weekly_wr",
    "median_win_pct_r",
)

DEFAULT_WEIGHTS = {
    "sharpe_ann": 1.0,
    "sortino_ann": 1.0,
    "std_daily": 1.0,
    "downside_dev_daily": 1.0,
    "mean_daily": 1.0,
    "pct_positive": 1.0,
    "max_dd": 3.0,  # F3/F4 weigh heaviest (PLAN §9.3)
    "recovery_days": 1.0,
    "weekly_wr": 1.5,
    "median_win_pct_r": 1.5,
    "curve_l2": 2.0,
}


def scalar_vector(fp: Fingerprints) -> np.ndarray:
    return np.array([getattr(fp, f) for f in SCALAR_FEATURES], dtype=np.float64)


def robust_scales(candidates: list[Fingerprints]) -> np.ndarray:
    mat = np.vstack([scalar_vector(fp) for fp in candidates])
    med = np.nanmedian(mat, axis=0)
    mad = np.nanmedian(np.abs(mat - med), axis=0)
    scale = 1.4826 * mad
    fallback = np.nanstd(mat, axis=0)
    scale = np.where(scale > 1e-12, scale, np.where(fallback > 1e-12, fallback, 1.0))
    return scale


def curve_l2(a: Fingerprints, b: Fingerprints) -> float:
    """L2 on log-VAMI, linearly resampled to the shorter curve's length."""
    x, y = a.log_vami, b.log_vami
    n = min(len(x), len(y))
    if n < 2:
        return float("nan")
    xi = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(x)), x)
    yi = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(y)), y)
    return float(np.sqrt(np.mean((xi - yi) ** 2)))


def dd_dates_ok(cand: Fingerprints, target: Fingerprints, tol_days: int = 2) -> bool:
    if target.dd_peak_date is None or target.dd_valley_date is None:
        return True
    if cand.dd_peak_date is None or cand.dd_valley_date is None:
        return False
    return (
        abs((cand.dd_peak_date - target.dd_peak_date).days) <= tol_days
        and abs((cand.dd_valley_date - target.dd_valley_date).days) <= tol_days
    )


def distance(
    cand: Fingerprints,
    target: Fingerprints,
    scales: np.ndarray,
    curve_scale: float,
    weights: dict[str, float] | None = None,
) -> float:
    w = weights or DEFAULT_WEIGHTS
    cv = scalar_vector(cand)
    tv = scalar_vector(target)
    z = (cv - tv) / scales
    wt = np.array([w[f] for f in SCALAR_FEATURES])
    valid = np.isfinite(z)
    if not valid.any():
        return float("inf")
    num = float(np.sum(wt[valid] * z[valid] ** 2))
    den = float(np.sum(wt[valid]))
    cl2 = curve_l2(cand, target)
    if np.isfinite(cl2) and curve_scale > 0:
        num += w["curve_l2"] * (cl2 / curve_scale) ** 2
        den += w["curve_l2"]
    return float(np.sqrt(num / den))


@dataclass(frozen=True)
class AbcResult:
    distances: np.ndarray  # inf where the hard DD-date gate failed
    eps: float
    accepted_idx: np.ndarray
    n_hard_pass: int


def abc_match(
    candidates: list[Fingerprints],
    target: Fingerprints,
    accept_frac: float = 0.01,
    dd_tol_days: int = 2,
    weights: dict[str, float] | None = None,
) -> AbcResult:
    scales = robust_scales(candidates)
    curve_ls = [curve_l2(fp, target) for fp in candidates]
    finite_cl = np.array([c for c in curve_ls if np.isfinite(c)])
    curve_scale = float(np.median(finite_cl)) if len(finite_cl) else 1.0

    dists = np.full(len(candidates), np.inf)
    for i, fp in enumerate(candidates):
        if not dd_dates_ok(fp, target, dd_tol_days):
            continue
        dists[i] = distance(fp, target, scales, curve_scale, weights)
    hard_pass = np.isfinite(dists)
    n_accept = max(round(accept_frac * len(candidates)), 1)
    if hard_pass.sum() == 0:
        return AbcResult(dists, float("inf"), np.array([], dtype=int), 0)
    order = np.argsort(dists)
    accepted = order[: min(n_accept, int(hard_pass.sum()))]
    eps = float(dists[accepted[-1]])
    return AbcResult(dists, eps, accepted, int(hard_pass.sum()))
