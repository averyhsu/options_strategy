import datetime as dt

import numpy as np
import polars as pl
import pytest

from options_strategy.data.calendar import ExpiryRules, build_expiry_table
from options_strategy.pricing.settlement import SettlementTable, settlement_intrinsic


def _table() -> SettlementTable:
    return SettlementTable(
        pl.DataFrame(
            {
                "expiry_date": [dt.date(2026, 3, 13), dt.date(2026, 3, 20), dt.date(2024, 3, 28)],
                "root": ["SPXW", "SPX", "SPXW"],
                "settlement": ["PM", "AM", "PM"],
                "value": [5057.31, 4930.25, 5210.40],
            }
        )
    )


def test_pm_itm_short_call_golden() -> None:
    # Hand-computed: settle 5057.31, K 5000 -> intrinsic 57.31 exactly.
    t = _table()
    v = t.value("SPXW", dt.date(2026, 3, 13))
    cash = settlement_intrinsic("C", 5000.0, v)
    assert abs(float(cash) - 57.31) < 1e-9
    assert t.settlement_kind("SPXW", dt.date(2026, 3, 13)) == "PM"


def test_am_itm_put_golden() -> None:
    # SET-style AM print 4930.25, K 5000 put -> 69.75 exactly.
    t = _table()
    v = t.value("SPX", dt.date(2026, 3, 20))
    assert abs(float(settlement_intrinsic("P", 5000.0, v)) - 69.75) < 1e-9
    assert t.settlement_kind("SPX", dt.date(2026, 3, 20)) == "AM"


def test_otm_settles_to_zero() -> None:
    v = _table().value("SPXW", dt.date(2026, 3, 13))
    assert float(settlement_intrinsic("C", 5100.0, v)) == 0.0
    assert float(settlement_intrinsic("P", 5000.0, v)) == 0.0


def test_vectorized_intrinsic() -> None:
    got = settlement_intrinsic(
        np.array(["C", "P", "C"]), np.array([5000.0, 5100.0, 5200.0]), 5057.31
    )
    np.testing.assert_allclose(got, [57.31, 42.69, 0.0], atol=1e-9)


def test_missing_settlement_refuses_to_guess() -> None:
    with pytest.raises(KeyError, match="refusing to guess"):
        _table().value("SPXW", dt.date(2026, 3, 12))
    # Root confusion must also fail loudly (PM weekly vs AM monthly, PLAN §14):
    with pytest.raises(KeyError):
        _table().value("SPX", dt.date(2026, 3, 13))


def test_holiday_shifted_expiry_settles_on_shifted_date() -> None:
    # Good Friday 2024-03-29: the weekly settles Thursday 03-28 (PM). The
    # settlement table is keyed by the SHIFTED date; the unshifted Friday has
    # no settlement row and must raise.
    expiries = build_expiry_table(dt.date(2024, 3, 1), dt.date(2024, 3, 31), ExpiryRules())
    weekly_dates = expiries.filter(pl.col("root") == "SPXW")["expiry_date"].to_list()
    assert dt.date(2024, 3, 28) in weekly_dates
    t = _table()
    assert t.value("SPXW", dt.date(2024, 3, 28)) == 5210.40
    with pytest.raises(KeyError):
        t.value("SPXW", dt.date(2024, 3, 29))
