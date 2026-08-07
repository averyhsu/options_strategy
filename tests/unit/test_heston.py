import datetime as dt

import numpy as np
import pytest

from options_strategy.data.calendar import load_sessions
from options_strategy.data.synthetic.config import (
    ForcedEvent,
    ScenarioSegment,
    SyntheticWorldConfig,
)
from options_strategy.data.synthetic.heston import FULL_SESSION_BARS, simulate


def _cfg(**overrides) -> SyntheticWorldConfig:
    base = {
        "name": "unit-synthetic",
        "start": dt.date(2024, 6, 3),
        "end": dt.date(2024, 7, 12),
        "seed": 7,
    }
    base.update(overrides)
    return SyntheticWorldConfig(**base)


@pytest.fixture(scope="module")
def sessions():
    return load_sessions(dt.date(2024, 6, 3), dt.date(2024, 7, 12))


def test_deterministic_regeneration(sessions) -> None:
    a = simulate(_cfg(), sessions)
    b = simulate(_cfg(), sessions)
    np.testing.assert_array_equal(a.s, b.s)
    np.testing.assert_array_equal(a.v, b.v)
    np.testing.assert_array_equal(a.ts, b.ts)


def test_seed_changes_path(sessions) -> None:
    a = simulate(_cfg(), sessions)
    b = simulate(_cfg(seed=8), sessions)
    assert not np.array_equal(a.s, b.s)


def test_bar_grid_respects_early_close(sessions) -> None:
    path = simulate(_cfg(), sessions)
    dates = path.session_dates.astype(object).tolist()
    i_full = dates.index(dt.date(2024, 6, 10))
    i_early = dates.index(dt.date(2024, 7, 3))  # 13:00 close
    assert path.session_n_bars[i_full] == FULL_SESSION_BARS
    assert path.session_n_bars[i_early] == 210
    first_bar = path.ts[path.session_start_idx[i_full]]
    assert str(first_bar).endswith("09:30:00.000000")


def test_variance_stays_nonnegative_under_stress(sessions) -> None:
    cfg = _cfg(
        heston={"v0": 0.01, "theta": 0.01, "kappa": 0.5, "xi": 1.5, "rho": -0.9},
        seed=123,
    )
    path = simulate(cfg, sessions)
    assert np.all(path.v >= 0.0)
    assert np.all(np.isfinite(path.s))


def test_forced_event_gap_is_exact(sessions) -> None:
    ev = ForcedEvent(session=dt.date(2024, 6, 24), gap_pct=-0.05, vol_mult=2.5)
    path = simulate(_cfg(forced_events=(ev,)), sessions)
    dates = path.session_dates.astype(object).tolist()
    i = dates.index(dt.date(2024, 6, 24))
    prev_close_idx = path.session_start_idx[i] - 1
    # First bar of the gapped session already includes one intraday step, so
    # compare the pre-step level: replay is exact because the forced event
    # replaces the stochastic overnight move entirely. We check via the jump in
    # log space between close and the first bar being dominated by the gap.
    ratio = path.s[path.session_start_idx[i]] / path.s[prev_close_idx]
    assert abs(ratio - 0.95) < 0.01  # one 1-min diffusion step of slack


def test_scenario_segments_change_drift(sessions) -> None:
    up = _cfg(segments=(ScenarioSegment(length_sessions=10_000, mu_annual=3.0),), seed=5)
    down = _cfg(segments=(ScenarioSegment(length_sessions=10_000, mu_annual=-3.0),), seed=5)
    a = simulate(up, sessions)
    b = simulate(down, sessions)
    # Same seed => same shocks; only drift differs, so the ratio must trend.
    assert a.s[-1] / a.s[0] > b.s[-1] / b.s[0]
