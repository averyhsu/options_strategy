"""Offline tests for the credit-check preview driver (synthetic chain, no vendor data)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from options_strategy.eval.credit_check_preview import (
    STUDY_JSON,
    band_edges_from_study,
    entry_dates_from_study,
    parity_fits,
    run_one_entry,
    write_report,
)
from options_strategy.pricing import black76

SESSION = dt.date(2024, 8, 2)
SPOT = 5347.0
DF_RATE = 0.05  # flat cc rate for the synthetic chain
EXPIRIES = [
    dt.date(2024, 8, 9),  # 7d front
    dt.date(2024, 8, 16),  # 14d front
    dt.date(2024, 8, 30),  # back for the 7d front (21d later)
    dt.date(2024, 9, 6),  # back for the 14d front
]


def _synthetic_chain(vol: float = 0.20, spread: float = 1.0) -> pl.DataFrame:
    rows = []
    strikes = np.arange(4900.0, 5800.0 + 1, 25.0)
    for expiry in EXPIRIES:
        tau = (expiry - SESSION).days / 365.0
        df = float(np.exp(-DF_RATE * tau))
        fwd = SPOT / df
        for k in strikes:
            for cp, w in (("C", 1), ("P", -1)):
                mid = float(black76.price(fwd, k, tau, vol, df, cp=w))
                bid = max(mid - spread / 2, 0.0)
                if bid <= 0:
                    continue
                rows.append(
                    {
                        "expiry_date": expiry,
                        "cp": cp,
                        "strike": float(k),
                        "bid": bid,
                        "ask": mid + spread / 2,
                    }
                )
    return pl.DataFrame(rows)


CHAIN = _synthetic_chain()
STUDY = json.loads(Path(STUDY_JSON).read_text())
EDGES = band_edges_from_study(STUDY)


def test_parity_fits_recover_forward_and_df() -> None:
    fits, diag = parity_fits(CHAIN, SESSION)
    assert set(fits) == set(EXPIRIES)
    for expiry, (fwd, df, tau) in fits.items():
        tau_true = (expiry - SESSION).days / 365.0
        assert tau == pytest.approx(tau_true)
        assert df == pytest.approx(np.exp(-DF_RATE * tau_true), rel=5e-3)
        assert fwd == pytest.approx(SPOT / np.exp(-DF_RATE * tau_true), rel=2e-3)
    assert diag["rmse_max"] < 0.5  # exact-parity mids, only spread rounding


def test_band_edges_cover_both_variants() -> None:
    assert set(EDGES) == {"7d", "14d"}
    for variant in EDGES.values():
        assert set(variant) == {"q85", "q90", "q95"}
        for put_edge, call_edge in variant.values():
            assert put_edge < 0 < call_edge
    # 14d bands are wider than 7d at the same q
    assert EDGES["14d"]["q90"][0] < EDGES["7d"]["q90"][0]


def test_entry_dates_are_the_two_preview_windows() -> None:
    entries = entry_dates_from_study(STUDY)
    by_window: dict[str, int] = {}
    for e in entries:
        by_window[e["window"]] = by_window.get(e["window"], 0) + 1
    assert by_window == {"vix-spike-aug-2024": 5, "live-window-2026": 18}


def test_run_one_entry_produces_both_variants_and_atm_ref() -> None:
    rows = run_one_entry(CHAIN, SPOT, SESSION, EDGES)
    assert set(rows["front_variant"].unique().to_list()) == {"7d", "14d"}
    assert "atm_ref" in rows["label"].to_list()
    assert set(rows["wing_offset"].unique().to_list()) == {0.0, 25.0, 50.0}
    # 7d structures use the 7-day front and the >=21d-later back
    seven = rows.filter(pl.col("front_variant") == "7d")
    assert seven["front_expiry"].unique().to_list() == [dt.date(2024, 8, 9)]
    assert seven["back_expiry"].unique().to_list() == [dt.date(2024, 8, 30)]
    # dual reading: both metrics finite, and the flags are consistent
    assert rows["net_premium_pct_risk"].is_finite().all()
    assert rows["max_gain_pct_risk"].is_finite().all()
    for r in rows.rows(named=True):
        assert r["is_debit"] == (r["net_premium"] < 0)
        assert r["thirty_pct_achievable"] == (r["max_gain_pct_risk"] >= 0.30)


def test_write_report_renders(tmp_path) -> None:
    rows = run_one_entry(CHAIN, SPOT, SESSION, EDGES).with_columns(
        pl.lit("vix-spike-aug-2024").alias("window"), pl.lit("bull").alias("ema_state")
    )
    out = tmp_path / "preview.md"
    write_report(rows, {"data_version": "vTEST", "n_entries_priced": 1,
                        "n_entries_skipped": 0, "skipped": [], "n_structures": rows.height}, out)
    text = out.read_text()
    assert "2 of 6 regimes, EOD basis" in text
    assert "vTEST" in text
    assert "atm_ref" in text
