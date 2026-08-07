import numpy as np

from options_strategy.engine.attribution import PositionDay, explain_day
from options_strategy.pricing.black76 import price as b76

RF = 0.0262


def _day(f: float, k: float, tau: float, iv: float, cp: int) -> PositionDay:
    df = float(np.exp(-RF * tau))
    return PositionDay(
        forward=f,
        strike=k,
        tau=tau,
        iv=iv,
        df=df,
        cp=cp,
        mark=float(b76(f, k, tau, iv, df, cp=cp)),
    )


def test_taylor_explains_normal_day_within_tolerance() -> None:
    """Invariant §11.5: delta/gamma/theta/vega explain non-gap daily P&L."""
    prev = _day(5000.0, 5100.0, 30 / 365, 0.200, cp=1)
    curr = _day(5040.0, 5100.0, 29 / 365, 0.205, cp=1)
    att = explain_day(prev, curr)
    assert not att.is_gap_day
    assert abs(att.actual) > 5.0  # a real move to explain
    assert abs(att.residual) < max(0.03 * abs(att.actual), 0.10)


def test_taylor_explains_quiet_day_tightly() -> None:
    prev = _day(5000.0, 4900.0, 14 / 365, 0.18, cp=-1)
    curr = _day(5004.0, 4900.0, 13 / 365, 0.179, cp=-1)
    att = explain_day(prev, curr)
    assert not att.is_gap_day
    assert abs(att.residual) < 0.05


def test_gap_day_is_flagged_and_residual_reported() -> None:
    prev = _day(5000.0, 4900.0, 14 / 365, 0.18, cp=-1)
    curr = _day(4600.0, 4900.0, 13 / 365, 0.32, cp=-1)  # -8% gap, vol spike
    att = explain_day(prev, curr)
    assert att.is_gap_day
    # Taylor is EXPECTED to fail here; the residual is reported, not excused.
    assert abs(att.residual) > 1.0
