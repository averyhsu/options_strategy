"""Vectorized Black-76 pricing on the forward (PLAN §6).

Options are European cash-settled; pricing is on the forward so dividends never
enter. `cp` is +1 for calls, -1 for puts (arrays allowed). At tau <= 0 or
sigma <= 0 prices collapse to discounted forward intrinsic.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr

# Total vols below this are numerically indistinguishable from expiry.
_MIN_TOTAL_VOL = 1e-12


def cp_sign(cp: np.ndarray | str) -> np.ndarray:
    """Map 'C'/'P' (str or array) to +1/-1."""
    arr = np.asarray(cp)
    if arr.dtype.kind in "US":
        return np.where(np.char.upper(arr.astype(str)) == "C", 1, -1)
    return arr.astype(np.int64)


def price(
    forward: np.ndarray | float,
    strike: np.ndarray | float,
    tau: np.ndarray | float,
    sigma: np.ndarray | float,
    df: np.ndarray | float = 1.0,
    cp: np.ndarray | int = 1,
) -> np.ndarray:
    """Black-76 price. tau in ACT/365 years; df discounts expiry -> valuation."""
    f = np.asarray(forward, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    t = np.asarray(tau, dtype=np.float64)
    s = np.asarray(sigma, dtype=np.float64)
    d = np.asarray(df, dtype=np.float64)
    w = np.asarray(cp_sign(cp) if not isinstance(cp, int) else cp, dtype=np.float64)

    f, k, t, s, d, w = np.broadcast_arrays(f, k, t, s, d, w)

    intrinsic = d * np.maximum(w * (f - k), 0.0)
    total_vol = s * np.sqrt(np.maximum(t, 0.0))
    live = (total_vol > _MIN_TOTAL_VOL) & (f > 0.0) & (k > 0.0)

    safe_vol = np.where(live, total_vol, 1.0)
    log_ratio = np.log(np.where(live, f, 1.0) / np.where(live, k, 1.0))
    d1 = log_ratio / safe_vol + 0.5 * safe_vol
    d2 = d1 - safe_vol
    bs = d * w * (f * ndtr(w * d1) - k * ndtr(w * d2))
    return np.where(live, bs, intrinsic)


def forward_intrinsic(
    forward: np.ndarray | float,
    strike: np.ndarray | float,
    df: np.ndarray | float = 1.0,
    cp: np.ndarray | int = 1,
) -> np.ndarray:
    f = np.asarray(forward, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    d = np.asarray(df, dtype=np.float64)
    w = np.asarray(cp_sign(cp) if not isinstance(cp, int) else cp, dtype=np.float64)
    return d * np.maximum(w * (f - k), 0.0)
