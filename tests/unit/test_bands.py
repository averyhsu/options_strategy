"""Percentile-band strike placement pure core (PLAN §8.1 default family)."""

import datetime as dt

import numpy as np
import polars as pl
import pytest

from options_strategy.strategy.bands import above_ema_next_returns, band_edges


def _daily_from_weekly_closes(closes: list[float]) -> pl.DataFrame:
    rows = []
    d = dt.date(2020, 1, 6)  # a Monday
    for c in closes:
        for k in range(5):
            day = d + dt.timedelta(days=k)
            rows.append(
                {"session": day, "open": c, "high": c * 1.002, "low": c * 0.998, "close": c}
            )
        d += dt.timedelta(weeks=1)
    return pl.DataFrame(rows)


def test_above_ema_next_returns_matches_hand_computation() -> None:
    # weekly closes: rising then one dip; ema_len=3 -> states from week 3
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 100.0, 105.0, 106.0]
    daily = _daily_from_weekly_closes(closes)
    arr = above_ema_next_returns(daily, ema_len=3)
    # states (ema3, SMA-seeded): weeks 0-1 warmup; weeks 2..7 vs EMA.
    # pairs (state_t == bull, ret_{t+1}) for t = 2..6
    ema = [None, None, 101.0]
    for c in closes[3:]:
        ema.append(c * 0.5 + ema[-1] * 0.5)
    states = [None, None] + [
        "bull" if c > e else "bear" for c, e in zip(closes[2:], ema[2:], strict=True)
    ]
    expected = [
        closes[t + 1] / closes[t] - 1.0 for t in range(len(closes) - 1) if states[t] == "bull"
    ]
    np.testing.assert_allclose(arr, expected, rtol=1e-12)


def test_above_ema_next_returns_empty_cases() -> None:
    assert len(above_ema_next_returns(pl.DataFrame(schema={"session": pl.Date}), 21)) == 0
    # too short for the EMA: all warmup -> empty
    short = _daily_from_weekly_closes([100.0, 101.0, 102.0])
    assert len(above_ema_next_returns(short, ema_len=21)) == 0


def test_band_edges_quantiles_and_min_obs() -> None:
    arr = np.linspace(-0.05, 0.05, 101)  # uniform grid
    edges = band_edges(arr, q_put=0.90, q_call=0.90, min_obs=50)
    assert edges is not None
    put_edge, call_edge = edges
    assert put_edge == pytest.approx(-0.04)
    assert call_edge == pytest.approx(0.04)
    # asymmetric coverages
    pe2, ce2 = band_edges(arr, q_put=0.95, q_call=0.80, min_obs=50)
    assert pe2 < put_edge and ce2 < call_edge
    # thin sample refuses to estimate
    assert band_edges(arr[:10], 0.90, 0.90, min_obs=50) is None
    assert band_edges(np.empty(0), 0.90, 0.90, min_obs=1) is None
