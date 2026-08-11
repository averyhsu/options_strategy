"""Candle-study pure functions (PLAN §8.3 expanded deliverable).

Tests run on constructed frames only — no network, no data/raw/free (CI has
neither). The real-data driver is exercised locally; its committed artifact
is checked by tests/integration/test_candle_study_artifact.py.
"""

import datetime as dt

import numpy as np
import polars as pl
import pytest

from options_strategy.eval.candle_study import (
    coverage_table,
    dist_stats,
    inverse_solve,
    losing_streaks,
    touch_calendar,
    weekly_conditional_frame,
)


def _daily(closes: list[float], start: dt.date = dt.date(2020, 1, 6)) -> pl.DataFrame:
    """One synthetic trading day per weekday, flat OHLC around the close path."""
    sessions, rows = [], []
    d = start
    for c in closes:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        sessions.append(d)
        rows.append({"session": d, "open": c, "high": c * 1.004, "low": c * 0.996, "close": c})
        d += dt.timedelta(days=1)
    return pl.DataFrame(rows)


def test_weekly_conditional_frame_no_lookahead() -> None:
    # 30 weeks of 5 flat days each; week k closes at 100 + k
    closes = [100.0 + k for k in range(30) for _ in range(5)]
    wk = weekly_conditional_frame(_daily(closes), ema_len=5)
    # next_ret at week t must equal week t+1 close / week t close - 1
    c = wk["close"].to_list()
    nr = wk["next_ret"].to_list()
    for i in range(len(c) - 1):
        assert nr[i] == pytest.approx(c[i + 1] / c[i] - 1.0)
    # rising tape: every post-warmup week is bull
    assert set(wk["state"].to_list()) == {"bull"}
    # the final (outcome-less) week is dropped
    assert wk["next_ret"].null_count() == 0


def test_dist_stats_and_coverage_on_known_distribution() -> None:
    rng = np.random.default_rng(7)
    rets = rng.uniform(-0.05, 0.05, size=5000)
    s = dist_stats(rets)
    assert s["n"] == 5000
    assert s["mean"] == pytest.approx(0.0, abs=0.002)
    assert s["frac_pos"] == pytest.approx(0.5, abs=0.03)

    above = pl.DataFrame(
        {
            "next_ret": rets,
            "next_low_ret": rets - 0.01,
            "next_high_ret": rets + 0.01,
            "week_end": [dt.date(2020, 1, 3)] * len(rets),
        }
    )
    cov = coverage_table(above, [0.90], spot=1000.0)
    r = cov.row(0, named=True)
    # uniform[-5%,5%]: q=0.90 edges at ±4%; P(inside) = 2q-1 = 0.80
    assert r["put_edge_ret"] == pytest.approx(-0.04, abs=0.002)
    assert r["call_edge_ret"] == pytest.approx(0.04, abs=0.002)
    assert r["p_inside_close"] == pytest.approx(0.80, abs=0.02)
    assert r["put_strike_dist_pts"] == pytest.approx(40.0, abs=2.0)
    # intraweek extremes overshoot closes by 1%: touch rate > close-outside rate
    assert r["p_touch_put"] > 1.0 - 0.90
    assert r["p_touch_any"] > r["p_touch_put"]


def test_inverse_solve_satisfies_kelly_identity() -> None:
    out = inverse_solve(p_win=0.88, win_pct_r=0.30, kelly=0.60, ev_per_contract=450.0)
    a, b, p = out["required_avg_loss_pct_r"], 0.30, 0.88
    # f* = p/a - (1-p)/b must reproduce the target Kelly
    assert p / a - (1 - p) / b == pytest.approx(0.60, abs=1e-12)
    assert out["ev_frac_of_r"] == pytest.approx(p * b - (1 - p) * a)
    assert out["implied_r_per_contract"] == pytest.approx(450.0 / out["ev_frac_of_r"])
    assert out["undefended_loss_pct_r"] == pytest.approx(0.70)
    # higher win prob must allow a larger tolerable loss at the same Kelly
    assert (
        inverse_solve(0.92)["required_avg_loss_pct_r"]
        > inverse_solve(0.85)["required_avg_loss_pct_r"]
    )


def test_losing_streaks_states_and_lengths() -> None:
    #        idx: 0    1     2     3     4    5     6     7     8
    rets = np.array([0.01, -0.01, -0.02, -0.01, 0.02, -0.01, -0.01, -0.03, -0.01])
    states = ["bull", "bull", "bear", "bear", "bear", "bear", "bear", "bear", "bull"]
    st = losing_streaks(rets, states, min_len=3)
    assert [s["length"] for s in st] == [3, 4]
    # first streak began at idx 1: entry-visible state is states[0] = bull
    assert st[0]["state_before"] == "bull"
    assert st[0]["any_bull_during"] is True
    # second streak began at idx 5: entry-visible state bear, all-bear until idx 8
    assert st[1]["state_before"] == "bear"
    assert st[1]["all_bear_during"] is False  # idx 8 is bull
    # streaks shorter than min_len are ignored
    assert losing_streaks(np.array([-0.01, -0.01, 0.01]), ["bull"] * 3, min_len=3) == []


def test_touch_calendar_counts() -> None:
    # 10 weeks in 2020, 10 in 2021; symmetric returns; extremes = close ± 2%
    rng = np.random.default_rng(3)
    rets = rng.uniform(-0.03, 0.03, 20)
    above = pl.DataFrame(
        {
            "week_end": [dt.date(2020, 1, 3) + dt.timedelta(weeks=i) for i in range(10)]
            + [dt.date(2021, 1, 8) + dt.timedelta(weeks=i) for i in range(10)],
            "next_ret": rets,
            "next_low_ret": rets - 0.02,
            "next_high_ret": rets + 0.02,
        }
    )
    cal = touch_calendar(above, [0.80])
    assert cal["year"].to_list() == [2020, 2021]
    assert cal["n_entry_weeks"].to_list() == [10, 10]
    # counts must equal a direct recomputation
    pe = float(np.quantile(rets, 0.20))
    expected_2020 = int(((rets[:10] - 0.02) <= pe).sum())
    assert cal["touch_put_q80"].to_list()[0] == expected_2020
