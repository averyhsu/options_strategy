import datetime as dt

import numpy as np
import pytest

from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.margin import (
    LegState,
    ScenarioGrid,
    contracts_for_risk,
    r_margin,
    r_scenario,
    r_width,
)

SPOT = 5000.0
FRONT = dt.date(2026, 3, 13)
BACK = dt.date(2026, 4, 2)
TAU_F, TAU_B = 7 / 365, 27 / 365
RF, Q = 0.0262, 0.013


def _leg(root, expiry, strike, cp, ratio, mid, iv, tau) -> LegState:
    fwd = SPOT * np.exp((RF - Q) * tau)
    return LegState(
        key=OptionKey(root, expiry, strike, cp),
        ratio=ratio,
        mid=mid,
        iv=iv,
        tau=tau,
        forward=float(fwd),
        df=float(np.exp(-RF * tau)),
    )


def _double_diagonal() -> list[LegState]:
    return [
        _leg("SPXW", FRONT, 5100.0, "C", -1, 10.0, 0.15, TAU_F),
        _leg("SPXW", FRONT, 4900.0, "P", -1, 12.0, 0.20, TAU_F),
        _leg("SPXW", BACK, 5150.0, "C", +1, 28.0, 0.16, TAU_B),
        _leg("SPXW", BACK, 4850.0, "P", +1, 34.0, 0.21, TAU_B),
    ]


def test_r_scenario_positive_and_bounded_by_widths() -> None:
    legs = _double_diagonal()
    r = r_scenario(legs, SPOT)
    assert r > 500.0  # a +/-12% grid must find real pain
    # Defined-risk-ish: cannot exceed both widths plus the net debit paid
    net_debit = sum(x.ratio * x.mid for x in legs)
    assert r <= (50.0 + 50.0 + max(net_debit, 0.0)) * 100.0


def test_r_scenario_worsens_with_vol_scenarios() -> None:
    legs = _double_diagonal()
    r_no_vol = r_scenario(legs, SPOT, ScenarioGrid(vol_shifts=(0.0,)))
    r_full = r_scenario(legs, SPOT)
    assert r_full >= r_no_vol


def test_r_width_and_r_margin_hand_computed() -> None:
    legs = _double_diagonal()
    net_debit = sum(x.ratio * x.mid for x in legs)  # 28+34-10-12 = 40 debit
    assert abs(r_width(legs) - (50.0 + net_debit) * 100.0) < 1e-9
    assert abs(r_margin(legs) - 5000.0) < 1e-9


def test_naked_short_refuses_width_models() -> None:
    naked = [_leg("SPXW", FRONT, 4900.0, "P", -1, 12.0, 0.2, TAU_F)]
    with pytest.raises(ValueError, match="naked"):
        r_width(naked)
    with pytest.raises(ValueError, match="naked"):
        r_margin(naked)
    assert r_scenario(naked, SPOT) > 0  # scenario model handles it fine


def test_contracts_for_risk() -> None:
    assert contracts_for_risk(0.15, 100_000.0, 4_500.0) == 3
    assert contracts_for_risk(0.15, 100_000.0, 20_000.0) == 0
    assert contracts_for_risk(0.15, 100_000.0, 0.0) == 0
