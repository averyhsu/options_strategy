"""SSVI implied-vol surface driven by the Heston state (PLAN §5).

theta_T (ATM total variance to expiry) is the Heston expected integrated
variance from the current v_t, so the surface breathes with the simulated vol
state. Slices are SSVI (Gatheral-Jacquier 2014): butterfly-arbitrage-free when
theta*phi*(1+|rho|) <= 4 and theta*phi^2*(1+|rho|) <= 4 (checked here), and
calendar-arbitrage-free because theta_T is strictly increasing in T.
"""

from __future__ import annotations

import numpy as np

from options_strategy.data.synthetic.config import HestonParams, SurfaceParams


def expected_total_variance(
    v_t: np.ndarray | float, tau: np.ndarray | float, h: HestonParams
) -> np.ndarray:
    """E[ integral_0^tau v_s ds ] under Heston: theta*tau + (v_t-theta)(1-e^{-k tau})/k."""
    v = np.asarray(v_t, dtype=np.float64)
    t = np.asarray(tau, dtype=np.float64)
    return h.theta * t + (v - h.theta) * (1.0 - np.exp(-h.kappa * t)) / h.kappa


def ssvi_total_variance(
    k: np.ndarray | float, theta_t: np.ndarray | float, p: SurfaceParams
) -> np.ndarray:
    kk = np.asarray(k, dtype=np.float64)
    th = np.asarray(theta_t, dtype=np.float64)
    phi = p.eta / th**p.gamma_
    x = phi * kk
    return 0.5 * th * (1.0 + p.rho * x + np.sqrt((x + p.rho) ** 2 + 1.0 - p.rho**2))


def implied_vol(
    k: np.ndarray | float,
    tau: np.ndarray | float,
    theta_t: np.ndarray | float,
    p: SurfaceParams,
) -> np.ndarray:
    w = ssvi_total_variance(k, theta_t, p)
    return np.sqrt(w / np.asarray(tau, dtype=np.float64))


def validate_no_butterfly(p: SurfaceParams, theta_min: float, theta_max: float) -> None:
    """Raise if the SSVI butterfly conditions fail anywhere in [theta_min, theta_max]."""
    if not (0.0 < theta_min <= theta_max):
        raise ValueError(f"invalid theta range [{theta_min}, {theta_max}]")
    if not (-1.0 < p.rho < 1.0) or p.eta <= 0.0 or not (0.0 < p.gamma_ < 1.0):
        raise ValueError(f"invalid SSVI params {p}")
    grid = np.geomspace(theta_min, theta_max, 64)
    phi = p.eta / grid**p.gamma_
    one_plus_rho = 1.0 + abs(p.rho)
    cond1 = grid * phi * one_plus_rho
    cond2 = grid * phi**2 * one_plus_rho
    if cond1.max() > 4.0 or cond2.max() > 4.0:
        raise ValueError(
            "SSVI butterfly-arbitrage condition violated: "
            f"max(theta*phi*(1+|rho|))={cond1.max():.3f}, "
            f"max(theta*phi^2*(1+|rho|))={cond2.max():.3f} (both must be <= 4)"
        )
