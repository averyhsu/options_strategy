"""The committed candle-study artifact (PLAN §8.3 expanded deliverable) must
exist, be labeled candles-only, and answer items (a)-(e)."""

import itertools
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_candle_study_report_exists_and_is_labeled() -> None:
    md = (REPO / "reports/candle_study.md").read_text()
    assert "CANDLES-ONLY" in md
    assert "No options positions are simulated" in md
    assert "Not investment advice" in md
    # items (a)-(e) all present
    for header in ["## (a)", "## (b)", "## (c)", "## (d)", "## (e)"]:
        assert header in md, f"missing section {header}"
    # sources labeled
    assert "yfinance" in md and "cboe" in md.lower() and "fred" in md.lower()
    # mini-purchase spec (2026-08-14): regime-stratified credit-check slice
    assert "## Mini-purchase specification" in md
    for window in (
        "calm-2017",
        "volmageddon-feb-2018",
        "covid-mar-2020",
        "bear-2022",
        "vix-spike-aug-2024",
        "live-window-2026",
    ):
        assert window in md, f"missing spec window {window}"


def test_purchase_spec_rows_are_consistent() -> None:
    res = json.loads((REPO / "reports/candle_study.json").read_text())
    spec = res["f_purchase_spec"]
    assert len(spec) >= 45
    for r in spec:
        spot = r["spot_close"]
        # ±4% window, snapped outward to 5-pt strikes
        assert r["strike_lo"] <= spot * 0.96 and r["strike_hi"] >= spot * 1.04
        assert r["strike_lo"] % 5 == 0 and r["strike_hi"] % 5 == 0
        assert r["front_expiry"] > r["entry_friday"]
        assert r["ema_state"] in ("bull", "bear")
    # the live fingerprint window must be fully sampled (weekly)
    live = [r for r in spec if r["window"] == "live-window-2026"]
    assert len(live) >= 16


def test_dual_reading_and_14d_variant_present() -> None:
    """2026-08-16 amendment: the spec must carry the debit-tolerant dual
    reading + ATM reference, and (e) gains the front_dte=14 variant."""
    md = (REPO / "reports/candle_study.md").read_text()
    assert "MUST NOT hard-fail debit structures" in md
    assert "near-ATM reference structure" in md.lower() or "A near-ATM reference structure" in md
    assert "### 14-day variant" in md
    res = json.loads((REPO / "reports/candle_study.json").read_text())
    cov14 = res["e_coverage_14d"]
    assert [r["q"] for r in cov14] == [0.85, 0.90, 0.95]
    # two-week edges must be at least as wide as the weekly ones at same q
    weekly = {r["q"]: r for r in res["b_coverage"]}
    for r in cov14:
        assert r["put_edge_ret"] <= weekly[r["q"]]["put_edge_ret"]
        assert r["call_edge_ret"] >= weekly[r["q"]]["call_edge_ret"]


def test_candle_study_json_answers_all_items() -> None:
    res = json.loads((REPO / "reports/candle_study.json").read_text())
    assert res["ema_len"] == 21
    assert res["n_weeks"] == res["n_above"] + res["n_below"]
    assert res["n_weeks"] > 1000  # 1999 -> present is ~1400 weeks
    # (a)
    assert res["a_dist_above"]["n"] == res["n_above"]
    assert res["a_dist_below"]["std"] > res["a_dist_above"]["std"]  # vol filter
    # (b) edges widen monotonically with q on the put side
    cov = res["b_coverage"]
    puts = [r["put_edge_ret"] for r in cov]
    assert all(a >= b for a, b in itertools.pairwise(puts))
    # (c) kelly identity holds for every solved row
    for r in res["c_inverse_solve"]:
        p, a = r["p_win"], r["required_avg_loss_pct_r"]
        assert abs(p / a - (1 - p) / 0.30 - 0.60) < 1e-9
    # (d) the verdict fields exist and are internally consistent
    d = res["d_streaks"]
    assert d["entered_in_bear"] + d["entered_in_bull"] <= d["n_streaks_ge3"]
    assert len(d["lengths"]) == d["n_streaks_ge3"]
    # (e) calendar covers the study window and counts <= entries
    cal = res["e_touch_calendar"]
    years = [r["year"] for r in cal]
    assert min(years) == 1999
    for r in cal:
        assert r["touch_put_q95"] <= r["touch_put_q80"] <= r["n_entry_weeks"]
