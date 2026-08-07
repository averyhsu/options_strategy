"""NBBO microstructure model: spreads, tick rounding, sizes (PLAN §5).

Half-spreads widen in the wings and under vol stress, with floors at the SPX
tick ($0.05 below a $3 premium, $0.10 at or above). Deep-OTM bids may round to
zero, which is a real market state, not a defect.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from options_strategy.data.synthetic.config import MicrostructureParams

TICK_BREAK = 3.0
TICK_LOW = 0.05
TICK_HIGH = 0.10
_SNAP_EPS = 1e-9


def tick_size(price: np.ndarray | float) -> np.ndarray:
    p = np.asarray(price, dtype=np.float64)
    return np.where(p < TICK_BREAK, TICK_LOW, TICK_HIGH)


def snap_to_tick(price: np.ndarray | float, side: int) -> np.ndarray:
    """Snap to the tick grid, band-consistently. side=-1 floors (bid), +1 ceils (ask)."""
    raw = np.maximum(np.asarray(price, dtype=np.float64), 0.0)
    p = raw
    for _ in range(2):  # second pass re-snaps values that crossed the $3 band
        t = tick_size(p)
        if side < 0:
            p = np.floor(raw / t + _SNAP_EPS) * t
        else:
            p = np.ceil(raw / t - _SNAP_EPS) * t
    return np.round(p, 10)


def is_on_tick(price: np.ndarray | float, atol: float = 1e-6) -> np.ndarray:
    p = np.asarray(price, dtype=np.float64)
    t = tick_size(p)
    return np.abs(p / t - np.round(p / t)) * t < atol


def half_width(
    mid: np.ndarray, k_norm: np.ndarray, v_ratio: np.ndarray | float, mp: MicrostructureParams
) -> np.ndarray:
    base = mp.half_width_abs + mp.half_width_frac * np.asarray(mid, dtype=np.float64)
    widen = (1.0 + mp.wing_widen * np.abs(k_norm)) * (
        1.0 + mp.stress_widen * np.maximum(np.asarray(v_ratio, dtype=np.float64) - 1.0, 0.0)
    )
    return np.maximum(mp.min_half_width, base * widen)


@dataclass(frozen=True)
class QuoteBlock:
    bid: np.ndarray
    ask: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray


def make_quotes(
    mid_theo: np.ndarray,
    k_norm: np.ndarray,
    v_ratio: np.ndarray | float,
    mp: MicrostructureParams,
    rng: np.random.Generator,
) -> QuoteBlock:
    hw = half_width(mid_theo, k_norm, v_ratio, mp)
    bid = snap_to_tick(mid_theo - hw, side=-1)
    ask = snap_to_tick(mid_theo + hw, side=+1)
    ask = np.where(ask <= bid, snap_to_tick(bid + tick_size(bid) * 1.001, side=+1), ask)

    n = mid_theo.shape[0]
    decay = np.exp(-0.5 * np.abs(k_norm))
    bid_size = np.clip(
        np.round(rng.lognormal(np.log(mp.size_median), mp.size_sigma, n) * decay), 1, 2000
    ).astype(np.int64)
    ask_size = np.clip(
        np.round(rng.lognormal(np.log(mp.size_median), mp.size_sigma, n) * decay), 1, 2000
    ).astype(np.int64)
    bid_size = np.where(bid <= 0.0, 0, bid_size)
    return QuoteBlock(bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)
