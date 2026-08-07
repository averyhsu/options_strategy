import datetime as dt

import pytest

from options_strategy.engine.instruments import INDEX, OptionKey
from options_strategy.engine.portfolio import EngineInvariantError, Portfolio

TS = dt.datetime(2026, 3, 6, 15, 59)
PUT = OptionKey("SPXW", dt.date(2026, 3, 13), 4900.0, "P")
CALL = OptionKey("SPXW", dt.date(2026, 3, 13), 5100.0, "C")
LEGS = ((PUT, -1), (CALL, -1))


def test_credit_fill_moves_cash_and_positions() -> None:
    p = Portfolio(100_000.0)
    p.apply_combo_fill(TS, 1, LEGS, qty=3, price_debit=-2.5, fees=9.60)
    assert abs(p.cash - (100_000.0 + 750.0 - 9.60)) < 1e-9
    assert p.positions[PUT] == -3 and p.positions[CALL] == -3
    marks = {PUT: 1.0, CALL: 1.2}
    nav = p.check_conservation(marks)
    assert abs(nav - (p.cash + (-3 * 1.0 - 3 * 1.2) * 100.0)) < 1e-9


def test_settlement_golden_short_put() -> None:
    p = Portfolio(50_000.0)
    p.apply_combo_fill(TS, 1, ((PUT, -1),), qty=2, price_debit=-8.0, fees=3.20)
    p.settle_expiry(PUT, settle_value=4850.0)  # 50 ITM against us
    # P&L = credit - intrinsic - fees = 1600 - 10000 - 3.20
    assert abs(p.cash - (50_000.0 + 1600.0 - 10_000.0 - 3.20)) < 1e-9
    assert PUT not in p.positions
    assert p.settlements[0].intrinsic == 50.0
    assert abs(p.check_conservation({}) - p.cash) < 1e-9


def test_otm_settlement_pays_zero() -> None:
    p = Portfolio(50_000.0)
    p.apply_combo_fill(TS, 1, ((PUT, -1),), qty=1, price_debit=-8.0, fees=1.60)
    p.settle_expiry(PUT, settle_value=4950.0)
    assert abs(p.cash - (50_000.0 + 800.0 - 1.60)) < 1e-9


def test_missing_mark_raises() -> None:
    p = Portfolio(10_000.0)
    p.apply_combo_fill(TS, 1, ((CALL, 1),), qty=1, price_debit=5.0, fees=1.60)
    with pytest.raises(EngineInvariantError, match="no mark"):
        p.nav({})


def test_index_unit_roundtrip() -> None:
    p = Portfolio(10_000.0)
    p.trade_index(2.0, 5000.0)
    assert p.cash == 0.0
    assert abs(p.nav({INDEX: 5100.0}) - 10_200.0) < 1e-9


def test_conservation_catches_cash_tampering() -> None:
    p = Portfolio(10_000.0)
    p.apply_combo_fill(TS, 1, ((CALL, 1),), qty=1, price_debit=5.0, fees=1.60)
    p.cash += 123.0  # corruption
    with pytest.raises(EngineInvariantError, match="reconstruction"):
        p.check_conservation({CALL: 5.0})
