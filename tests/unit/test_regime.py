import datetime as dt

import numpy as np
import polars as pl
import pytest

from options_strategy.strategy.regime import (
    EVENT_CROSSOVER,
    EVENT_NONE,
    EVENT_REJECTION,
    EVENT_RETRACEMENT,
    RegimeConfig,
    reference_events,
    regime_frame,
    weekly_bars,
)


def _daily_from_weekly(weekly: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """Expand weekly OHLC into Mon-Fri dailies that re-aggregate exactly."""
    rows = []
    monday = dt.date(2020, 1, 6)
    for i, (o, h, low, c) in enumerate(weekly):
        days = [monday + dt.timedelta(days=7 * i + d) for d in range(5)]
        mid = (o + c) / 2
        specs = [
            (o, max(o, mid), min(o, mid), mid),
            (mid, max(mid, c), min(mid, c), mid),
            (mid, h, mid if mid < h else h, mid),  # week high day
            (mid, mid, low, mid),  # week low day
            (mid, max(mid, c), min(mid, c), c),
        ]
        for day, (do, dh, dl, dc) in zip(days, specs, strict=True):
            rows.append({"session": day, "open": do, "high": dh, "low": dl, "close": dc})
    return pl.DataFrame(rows)


def _scripted_weekly() -> list[tuple[float, float, float, float]]:
    wk = [(100.0, 100.2, 99.8, 100.0)] * 21  # warmup: EMA pins at 100
    wk += [
        (100.0, 105.2, 99.9, 105.0),  # bull crossover
        (105.0, 106.5, 100.5, 106.0),  # dips to EMA, closes above -> retracement
        (106.0, 106.2, 94.8, 95.0),  # bear crossover
        (95.0, 100.6, 94.8, 96.0),  # rallies into EMA, closes below -> rejection
        (96.0, 96.2, 95.8, 96.0),  # quiet bear week -> none
    ]
    return wk


def test_weekly_bars_reaggregate_exactly() -> None:
    weekly = _scripted_weekly()
    wk = weekly_bars(_daily_from_weekly(weekly))
    assert wk.height == len(weekly)
    got = list(zip(wk["open"], wk["high"], wk["low"], wk["close"], strict=True))
    for a, b in zip(got, weekly, strict=True):
        assert a == pytest.approx(b)


def test_scripted_events_hit_every_type_and_match_reference() -> None:
    weekly = _scripted_weekly()
    cfg = RegimeConfig(ema_len=21, atr_len=14, hysteresis_atr=0.0)
    frame = regime_frame(_daily_from_weekly(weekly), cfg)
    ref = reference_events(weekly, cfg.ema_len, cfg.atr_len, cfg.hysteresis_atr)
    assert list(zip(frame["state"], frame["event"], strict=True)) == ref
    assert frame["event"].to_list()[21:26] == [
        EVENT_CROSSOVER,
        EVENT_RETRACEMENT,
        EVENT_CROSSOVER,
        EVENT_REJECTION,
        EVENT_NONE,
    ]


@pytest.mark.parametrize("ema_len,atr_len,h", [(21, 14, 0.0), (13, 14, 0.25), (34, 10, 0.5)])
def test_production_matches_reference_on_random_walk(ema_len: int, atr_len: int, h: float) -> None:
    """PLAN §12 P3 AC: regime events match a reference implementation."""
    rng = np.random.default_rng(7)
    n = 160
    rets = rng.normal(0.001, 0.025, n)
    closes = 4000.0 * np.exp(np.cumsum(rets))
    weekly = []
    prev_close = closes[0]
    for i in range(n):
        c = closes[i]
        hi = max(prev_close, c) * (1 + abs(rng.normal(0, 0.01)))
        lo = min(prev_close, c) * (1 - abs(rng.normal(0, 0.01)))
        weekly.append((prev_close, hi, lo, c))
        prev_close = c
    cfg = RegimeConfig(ema_len=ema_len, atr_len=atr_len, hysteresis_atr=h)
    frame = regime_frame(_daily_from_weekly(weekly), cfg)
    ref = reference_events(weekly, ema_len, atr_len, h)
    assert list(zip(frame["state"], frame["event"], strict=True)) == ref
    # sanity: the walk generated real signal, not all "none"
    events = frame["event"].to_list()
    assert events.count(EVENT_CROSSOVER) >= 2
