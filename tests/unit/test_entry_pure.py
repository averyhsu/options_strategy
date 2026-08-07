import datetime as dt
from zoneinfo import ZoneInfo

from options_strategy.strategy.entry import (
    EntryConfig,
    in_entry_window,
    rung_credit_thresholds,
    split_quantity,
    window_end,
)

ET = ZoneInfo("America/New_York")


def test_rung_thresholds_ascend() -> None:
    cfg = EntryConfig(credit_threshold_frac=0.30, ladder_rungs=3, ladder_step_frac=0.05)
    got = rung_credit_thresholds(cfg, reference=50.0)
    assert got == [15.0, 17.5, 20.0]


def test_split_quantity_front_loads_remainder() -> None:
    assert split_quantity(7, 3) == [3, 2, 2]
    assert split_quantity(2, 3) == [1, 1, 0]
    assert split_quantity(0, 2) == [0, 0]


def test_friday_window() -> None:
    cfg = EntryConfig(order_window="fri_open_close")
    fri = dt.date(2026, 3, 6)
    ts = dt.datetime(2026, 3, 6, 10, 0, tzinfo=ET)
    assert in_entry_window(ts, fri, True, False, cfg)
    assert not in_entry_window(ts, fri - dt.timedelta(days=1), False, True, cfg)


def test_thu14_window_opens_thursday_afternoon() -> None:
    cfg = EntryConfig(order_window="thu14_fri_close")
    thu = dt.date(2026, 3, 5)
    at_1359 = dt.datetime(2026, 3, 5, 13, 59, tzinfo=ET)
    at_1400 = dt.datetime(2026, 3, 5, 14, 0, tzinfo=ET)
    assert not in_entry_window(at_1359, thu, False, True, cfg)
    assert in_entry_window(at_1400, thu, False, True, cfg)
    # and any bar of the entry session itself:
    fri_am = dt.datetime(2026, 3, 6, 9, 30, tzinfo=ET)
    assert in_entry_window(fri_am, dt.date(2026, 3, 6), True, False, cfg)


def test_window_end_is_entry_session_close() -> None:
    end = window_end(dt.date(2026, 3, 6))
    assert end == dt.datetime(2026, 3, 6, 16, 0, tzinfo=ET)
