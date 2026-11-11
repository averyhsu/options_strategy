"""Offline tests for the touch-week tick fetcher's pure logic."""

from __future__ import annotations

import datetime as dt

import polars as pl

from options_strategy.data.vendors.theta_ticks import (
    _round5,
    dedup_quote_changes,
    resolve_expiries,
    week_contracts,
)


def test_round5() -> None:
    assert _round5(5347.2) == 5345.0
    assert _round5(5347.6) == 5350.0
    assert _round5(5000.0) == 5000.0


def test_resolve_expiries_uses_listed_dates_with_holiday_shift() -> None:
    week_end = dt.date(2020, 4, 3)
    listed = [
        dt.date(2020, 4, 3),  # entry day itself: excluded (0 DTE)
        dt.date(2020, 4, 9),  # Good-Friday-shifted Thursday front (6 days)
        dt.date(2020, 4, 17),
        dt.date(2020, 5, 1),  # first listed >= front+21d
        dt.date(2020, 5, 15),
    ]
    assert resolve_expiries(week_end, listed) == (dt.date(2020, 4, 9), dt.date(2020, 5, 1))
    # nothing inside 9 days -> unresolvable
    assert resolve_expiries(dt.date(2020, 4, 3), [dt.date(2020, 5, 1)]) is None


def test_week_contracts_shape_and_dedup() -> None:
    row = {
        "k_put_q85": 4950.0,
        "k_call_q85": 5050.0,
        "k_put_q90": 4925.0,
        "k_call_q90": 5075.0,
        "k_put_q95": 4900.0,
        "k_call_q95": 5100.0,
    }
    front, back = dt.date(2022, 3, 11), dt.date(2022, 4, 1)
    legs = week_contracts(row, front, back)
    assert len(legs) == 8  # 6 front shorts + 2 back wings
    fronts = [leg for leg in legs if leg["expiration"] == front]
    backs = [leg for leg in legs if leg["expiration"] == back]
    assert len(fronts) == 6 and len(backs) == 2
    assert {(b["strike"], b["right"]) for b in backs} == {(4900.0, "put"), (5100.0, "call")}
    # colliding strikes dedupe
    row_same = dict.fromkeys(row, 5000.0)
    legs_same = week_contracts(row_same, front, back)
    assert len(legs_same) == 2 + 2  # put/call at 5000 + two wings


def test_dedup_quote_changes_keeps_first_and_changes() -> None:
    df = pl.DataFrame(
        {
            "bid": [1.0, 1.0, 1.1, 1.1, 1.1],
            "ask": [1.2, 1.2, 1.2, 1.2, 1.3],
            "bid_size": [5, 5, 5, 5, 5],
            "ask_size": [5, 5, 5, 5, 5],
        }
    )
    out = dedup_quote_changes(df)
    assert out.height == 3  # first row, bid change, ask change


def test_resolve_expiries_prefers_friday_over_wednesday() -> None:
    week_end = dt.date(2021, 6, 18)  # Friday
    listed = [
        dt.date(2021, 6, 21),  # Mon +3: outside window
        dt.date(2021, 6, 23),  # Wed +5: in window but NOT the front
        dt.date(2021, 6, 25),  # Fri +7: the true front
        dt.date(2021, 7, 16),
    ]
    front, back = resolve_expiries(week_end, listed)
    assert front == dt.date(2021, 6, 25)
    assert back == dt.date(2021, 7, 16)
    # holiday-shifted Thursday front (+6) still wins when no +7 exists
    listed_shifted = [dt.date(2021, 6, 24), dt.date(2021, 7, 16)]
    front2, _ = resolve_expiries(week_end, listed_shifted)
    assert front2 == dt.date(2021, 6, 24)
