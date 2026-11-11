"""Credit-check dual metrics (PLAN §1.6 2026-08-16): the signed-premium and
debit return-on-risk readings must both compute, and debits must never be
rejected. Constructed chains only — the synthetic-world validation lives in
tests/integration/test_credit_check_synthetic.py."""

import datetime as dt

import polars as pl
import pytest

from options_strategy.eval.credit_check import (
    run_credit_check,
    structure_metrics,
)

FRONT = dt.date(2026, 3, 13)
BACK = dt.date(2026, 4, 2)
SESSION = dt.date(2026, 3, 6)


def _chain(rows: list[tuple[dt.date, str, float, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"expiry_date": e, "cp": cp, "strike": k, "bid": b, "ask": a} for e, cp, k, b, a in rows]
    )


def _fits(spot: float = 5000.0) -> dict:
    # flat forwards at spot, DF ~ 1: keeps hand arithmetic clean
    return {FRONT: (spot, 1.0, 7 / 365), BACK: (spot, 1.0, 27 / 365)}


def _quotes(mid: float, half: float = 0.5) -> tuple[float, float]:
    return mid - half, mid + half


def test_pure_calendar_debit_metrics_hand_case() -> None:
    # front strangle mids 10 + 8 = 18; back wings at the SAME strikes cost
    # 16 + 14 = 30 -> net premium = 18 - 30 = -12 (a 12-pt DEBIT)
    rows = [
        (FRONT, "P", 4900.0, *_quotes(10.0)),
        (FRONT, "C", 5100.0, *_quotes(8.0)),
        (BACK, "P", 4900.0, *_quotes(16.0)),
        (BACK, "C", 5100.0, *_quotes(14.0)),
    ]
    m = structure_metrics(_chain(rows), 5000.0, _fits(), FRONT, BACK, 4900.0, 5100.0, 0.0, "hand")
    assert m is not None
    assert m.net_premium == pytest.approx(-12.0)
    assert m.is_debit is True
    # pure calendar: width 0 -> risk = the debit paid
    assert m.risk_points == pytest.approx(12.0)
    assert m.net_premium_pct_risk == pytest.approx(-1.0)
    # a debit is REPORTED, not rejected, and reading (b) computes
    import math

    assert math.isfinite(m.max_gain_pct_risk)
    # at the short strikes the back legs retain time value while the front
    # shorts pin near zero: max gain in band must exceed -risk and, for this
    # richly-priced back month, be positive
    assert m.max_gain_pct_risk > 0.0
    assert m.thirty_pct_achievable in (True, False)


def test_credit_structure_positive_premium() -> None:
    # cheap far wings -> credit package: 18 collected vs 3 + 2 paid
    rows = [
        (FRONT, "P", 4900.0, *_quotes(10.0)),
        (FRONT, "C", 5100.0, *_quotes(8.0)),
        (BACK, "P", 4800.0, *_quotes(3.0)),
        (BACK, "C", 5200.0, *_quotes(2.0)),
    ]
    m = structure_metrics(_chain(rows), 5000.0, _fits(), FRONT, BACK, 4900.0, 5100.0, 100.0, "hand")
    assert m is not None
    assert m.net_premium == pytest.approx(13.0)
    assert m.is_debit is False
    # width 100, net debit -13 -> risk 87
    assert m.risk_points == pytest.approx(87.0)
    assert m.net_premium_pct_risk == pytest.approx(13.0 / 87.0)


def test_run_credit_check_adds_atm_reference_and_band_labels() -> None:
    strikes = [4800.0, 4900.0, 4950.0, 5000.0, 5050.0, 5100.0, 5200.0]
    rows = []
    for e, base in ((FRONT, 8.0), (BACK, 14.0)):
        for k in strikes:
            for cp in ("P", "C"):
                rows.append((e, cp, k, *_quotes(base)))
    df = run_credit_check(
        _chain(rows),
        spot=5000.0,
        fits=_fits(),
        session=SESSION,
        band_edges={"q90": (-0.02, 0.02)},
        wing_offsets=(0.0, 50.0),
        back_offset_days=20,
    )
    assert set(df["label"].unique().to_list()) == {"q90", "atm_ref"}
    # atm_ref shorts sit at / just outside spot
    atm = df.filter(pl.col("label") == "atm_ref").row(0, named=True)
    assert atm["short_put"] == 5000.0 and atm["short_call"] == 5000.0
    # q90 shorts land at the nearest strikes to spot*(1±2%)
    q90 = df.filter(pl.col("label") == "q90").row(0, named=True)
    assert q90["short_put"] == 4900.0 and q90["short_call"] == 5100.0
    # every row carries both readings
    assert df["net_premium_pct_risk"].is_finite().all()
    assert df["max_gain_pct_risk"].is_finite().all()


FITS14 = {FRONT: (5000.0, 1.0, 14 / 365), BACK: (5000.0, 1.0, 35 / 365)}
HAND_ROWS = [
    (FRONT, "P", 4900.0, *_quotes(10.0)),
    (FRONT, "C", 5100.0, *_quotes(8.0)),
    (BACK, "P", 4900.0, *_quotes(16.0)),
    (BACK, "C", 5100.0, *_quotes(14.0)),
]


def test_exit_mode_variant_labels_and_differs_from_hold() -> None:
    hold = structure_metrics(
        _chain(HAND_ROWS), 5000.0, FITS14, FRONT, BACK, 4900.0, 5100.0, 0.0, "hand"
    )
    early = structure_metrics(
        _chain(HAND_ROWS),
        5000.0,
        FITS14,
        FRONT,
        BACK,
        4900.0,
        5100.0,
        0.0,
        "hand",
        exit_dte=7,
    )
    assert hold is not None and early is not None
    assert hold.exit_mode == "hold_to_expiry"
    assert early.exit_mode == "exit_at_7dte"
    # entry pricing identical; only the horizon valuation moves
    assert early.net_premium == hold.net_premium
    assert early.risk_points == hold.risk_points
    import math

    assert math.isfinite(early.max_gain_pct_risk)
    assert early.max_gain_pct_risk != pytest.approx(hold.max_gain_pct_risk)


def test_exit_horizon_at_or_past_front_expiry_is_rejected() -> None:
    # 7d front with a 7d-before-expiry exit -> horizon 0: no valid variant
    m = structure_metrics(
        _chain(HAND_ROWS),
        5000.0,
        _fits(),
        FRONT,
        BACK,
        4900.0,
        5100.0,
        0.0,
        "hand",
        exit_dte=7,
    )
    assert m is None


def test_run_credit_check_exit_dtes_dimension() -> None:
    strikes = [4800.0, 4900.0, 4950.0, 5000.0, 5050.0, 5100.0, 5200.0]
    rows = []
    for e, base in ((FRONT, 8.0), (BACK, 14.0)):
        for k in strikes:
            for cp in ("P", "C"):
                rows.append((e, cp, k, *_quotes(base)))
    df = run_credit_check(
        _chain(rows),
        spot=5000.0,
        fits=FITS14,
        session=SESSION,
        band_edges={"q90": (-0.02, 0.02)},
        wing_offsets=(0.0,),
        front_dte_window=(5, 9),
        back_offset_days=20,
        exit_dtes=(None, 7),
    )
    assert set(df["exit_mode"].unique().to_list()) == {"hold_to_expiry", "exit_at_7dte"}
    # every (label, wing) pair appears once per exit mode
    counts = df.group_by("label", "wing_offset").len()
    assert counts["len"].unique().to_list() == [2]
