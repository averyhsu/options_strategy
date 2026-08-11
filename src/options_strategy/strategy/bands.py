"""Percentile-band strike placement (PLAN §8.1, amended 2026-08-10).

Per the author's disclosure his backtest was candles-only, so the only strike
rule that study could produce is: short strikes at percentiles of the trailing
above-EMA weekly-return distribution. This module is the shared pure core —
`build_diagonal` (Tracks A/B) and the fast sweep runner must both call it so
the equivalence tests keep the three paths identical.

No lookahead: callers pass daily history STRICTLY BEFORE the entry session
(`MarketView.daily_history` / the precompute prefix), so the distribution at
entry uses only completed weeks the trader could have seen.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from options_strategy.strategy.regime import RegimeConfig, regime_frame


def above_ema_next_returns(daily: pl.DataFrame, ema_len: int) -> np.ndarray:
    """Chronological next-week returns of weeks whose close sat above the EMA.

    daily: [session, open, high, low, close] strictly before the entry
    session. Pairs (state week t, return week t+1) over completed weeks —
    exactly the conditional distribution of the author's stated backtest.
    """
    if daily.height == 0:
        return np.empty(0)
    frame = regime_frame(daily, RegimeConfig(ema_len=ema_len))
    close = frame["close"].to_numpy()
    if len(close) < 2:
        return np.empty(0)
    state = frame["state"].to_list()
    rets = close[1:] / close[:-1] - 1.0
    mask = np.array([s == "bull" for s in state[:-1]], dtype=bool)
    return rets[mask]


def band_edges(
    arr: np.ndarray, q_put: float, q_call: float, min_obs: int
) -> tuple[float, float] | None:
    """(put_edge, call_edge) returns at one-sided coverages, or None while the
    trailing sample is too thin to estimate the band (entry is then skipped —
    the honest analog of 'not enough history to run his study')."""
    if len(arr) < min_obs:
        return None
    return float(np.quantile(arr, 1.0 - q_put)), float(np.quantile(arr, q_call))
