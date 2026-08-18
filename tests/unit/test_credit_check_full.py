"""Gate/corner logic for the full six-regime credit check (constructed rows)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from options_strategy.eval.credit_check_full import corner_rows, gate_result


def _row(window: str, session: dt.date, variant: str, label: str, ok: bool) -> dict:
    return {
        "window": window,
        "session": session,
        "front_variant": variant,
        "label": label,
        "wing_offset": 25.0,
        "exit_mode": "hold_to_expiry",
        "thirty_pct_achievable": ok,
        "net_premium_pct_risk": -0.7,
    }


def test_corner_excludes_7d_and_low_q() -> None:
    rows = pl.DataFrame(
        [
            _row("calm-2017", dt.date(2017, 1, 6), "14d", "q90", True),
            _row("calm-2017", dt.date(2017, 1, 6), "14d", "q85", True),  # low q: out
            _row("calm-2017", dt.date(2017, 1, 6), "7d", "q90", True),  # 7d: out
            _row("calm-2017", dt.date(2017, 1, 6), "14d", "atm_ref", False),
        ]
    )
    c = corner_rows(rows)
    assert c.height == 2
    assert set(c["label"].to_list()) == {"q90", "atm_ref"}


def test_gate_pause_when_three_regimes_below_20pct() -> None:
    rows = []
    # calm-2017: 5 dates, only 1 achieves in the corner (20% -> NOT below)
    for i in range(5):
        rows.append(_row("calm-2017", dt.date(2017, 1, 6 + i), "14d", "q90", i == 0))
    # three regimes with 4 dates each, none achieving -> below
    for w, y in (("volmageddon-feb-2018", 2018), ("covid-mar-2020", 2020), ("bear-2022", 2022)):
        for i in range(4):
            rows.append(_row(w, dt.date(y, 3, 3 + i), "14d", "q95", False))
    g = gate_result(pl.DataFrame(rows))
    assert g["per_regime"]["calm-2017"]["frac_dates_30pct"] == 0.2
    assert g["n_regimes_below_20pct"] == 3
    assert g["pause"] is True


def test_gate_continue_when_two_regimes_pass() -> None:
    rows = []
    for w, y, ok in (
        ("calm-2017", 2017, True),
        ("volmageddon-feb-2018", 2018, True),
        ("covid-mar-2020", 2020, False),
        ("bear-2022", 2022, False),
    ):
        for i in range(4):
            rows.append(_row(w, dt.date(y, 3, 3 + i), "14d", "q90", ok))
    g = gate_result(pl.DataFrame(rows))
    assert g["n_regimes_below_20pct"] == 2
    assert g["pause"] is False


def test_gate_any_corner_structure_counts_per_date() -> None:
    d = dt.date(2022, 1, 7)
    rows = pl.DataFrame(
        [
            _row("bear-2022", d, "14d", "q90", False),
            _row("bear-2022", d, "14d", "q95", True),  # one success flips the date
        ]
    )
    g = gate_result(rows)
    assert g["per_regime"]["bear-2022"]["frac_dates_30pct"] == 1.0
