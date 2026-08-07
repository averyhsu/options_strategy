"""Vectorized Black-76 implied vol: safeguarded Newton with Corrado-Miller
seeds and a bisection fallback (PLAN §6). Deep-ITM inputs are rotated to the
OTM option via put-call parity before solving (same vol, better conditioning).

Contract: round-trip |price(iv(p)) - p| <= 1e-6 wherever the input price is
strictly inside the no-arbitrage band (golden-tested on a strike/DTE/vol grid).
Prices at or outside the band return NaN.
"""

from __future__ import annotations

import numpy as np

from options_strategy.pricing.black76 import cp_sign
from options_strategy.pricing.black76 import price as b76_price

SIGMA_LO = 1e-5
SIGMA_HI = 6.0
_NEWTON_STEPS = 20
_BISECT_STEPS = 100
_TOL = 1e-9


def _corrado_miller_seed(
    p_fwd: np.ndarray, f: np.ndarray, k: np.ndarray, tau: np.ndarray
) -> np.ndarray:
    """Seed for the OTM-call-equivalent undiscounted price. Falls back to 0.25."""
    with np.errstate(invalid="ignore"):
        x = p_fwd - np.maximum(f - k, 0.0) / 2.0 + (f - k) / 2.0  # ~ call adjustment
        a = x - (f - k) / 2.0
        inner = a**2 - ((f - k) ** 2) / np.pi
        seed = (np.sqrt(2.0 * np.pi) / (f + k)) * (a + np.sqrt(np.maximum(inner, 0.0)))
        sigma = seed / np.sqrt(np.maximum(tau, 1e-12))
    return np.where(np.isfinite(sigma) & (sigma > SIGMA_LO), np.minimum(sigma, SIGMA_HI), 0.25)


def implied_vol(
    target_price: np.ndarray | float,
    forward: np.ndarray | float,
    strike: np.ndarray | float,
    tau: np.ndarray | float,
    df: np.ndarray | float = 1.0,
    cp: np.ndarray | int = 1,
) -> np.ndarray:
    p = np.asarray(target_price, dtype=np.float64)
    f = np.asarray(forward, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    t = np.asarray(tau, dtype=np.float64)
    d = np.asarray(df, dtype=np.float64)
    w = np.asarray(cp_sign(cp) if not isinstance(cp, int) else cp, dtype=np.float64)
    p, f, k, t, d, w = (a.copy() for a in np.broadcast_arrays(p, f, k, t, d, w))

    # Rotate ITM options to their OTM counterpart via parity: same vol.
    itm = w * (f - k) > 0.0
    p = np.where(itm, p - d * w * (f - k), p)
    w = np.where(itm, -w, w)

    p_fwd = p / d  # undiscounted OTM price
    intrinsic = np.maximum(w * (f - k), 0.0)  # zero after rotation (kept for clarity)
    upper = np.where(w > 0, f, k)
    solvable = (
        (t > 0.0)
        & (f > 0.0)
        & (k > 0.0)
        & (d > 0.0)
        & (p_fwd > intrinsic + 1e-12)
        & (p_fwd < upper - 1e-12)
    )

    sigma = _corrado_miller_seed(p_fwd, f, k, t)
    sigma = np.clip(sigma, SIGMA_LO, SIGMA_HI)

    sqrt_t = np.sqrt(np.maximum(t, 1e-300))
    for _ in range(_NEWTON_STEPS):
        model = b76_price(f, k, t, sigma, 1.0, cp=w)
        diff = model - p_fwd
        d1 = np.log(f / k) / (sigma * sqrt_t) + 0.5 * sigma * sqrt_t
        vega = f * np.exp(-0.5 * d1 * d1) / np.sqrt(2.0 * np.pi) * sqrt_t
        step = np.where(vega > 1e-12, diff / np.maximum(vega, 1e-12), 0.0)
        sigma = np.clip(sigma - step, SIGMA_LO, SIGMA_HI)

    model = b76_price(f, k, t, sigma, 1.0, cp=w)
    need_bisect = solvable & (np.abs(model - p_fwd) > _TOL)
    if np.any(need_bisect):
        lo = np.full_like(sigma, SIGMA_LO)
        hi = np.full_like(sigma, SIGMA_HI)
        for _ in range(_BISECT_STEPS):
            mid_s = 0.5 * (lo + hi)
            pm = b76_price(f, k, t, mid_s, 1.0, cp=w)
            go_up = pm < p_fwd
            lo = np.where(need_bisect & go_up, mid_s, lo)
            hi = np.where(need_bisect & ~go_up, mid_s, hi)
        sigma = np.where(need_bisect, 0.5 * (lo + hi), sigma)

    return np.where(solvable, sigma, np.nan)
