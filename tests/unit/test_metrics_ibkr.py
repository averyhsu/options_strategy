"""Invariant §11.8: the PLAN §2.1 reconstruction golden — a series with the
screenshot's exact daily moments must reproduce Sharpe 2.99 / Sortino 4.45 at
rf 2.62%/yr."""

import numpy as np
import pytest

from options_strategy.eval.metrics_ibkr import compute_metrics, daily_returns

TARGET_MEAN = 0.0047
TARGET_STD = 0.0244
TARGET_DD_DEV = 0.0164
RF = 0.0262


def _series_with_exact_moments(n: int = 87, seed: int = 5) -> np.ndarray:
    """Construct returns with EXACT sample mean/std and the target downside
    deviation vs the rf floor (two-group construction, then affine fix-up)."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 1, n)
    r = (r - r.mean()) / r.std(ddof=1)  # exact mean 0, sample std 1
    r = TARGET_MEAN + TARGET_STD * r
    # iterative scaling of the downside to hit the dd target while restoring
    # mean/std each pass (converges fast; verified by the assertions below)
    rf_d = RF / 252.0
    for _ in range(400):
        down = np.minimum(r - rf_d, 0.0)
        cur = np.sqrt(np.mean(down**2))
        if abs(cur - TARGET_DD_DEV) < 1e-12:
            break
        mask = r < rf_d
        r[mask] = rf_d + (r[mask] - rf_d) * (TARGET_DD_DEV / cur)
        r = (r - r.mean()) / r.std(ddof=1) * TARGET_STD + TARGET_MEAN
    return r


def test_plan_2_1_reconstruction_golden() -> None:
    r = _series_with_exact_moments()
    # the constructor must actually hit the moments, or the golden is vacuous
    assert r.mean() == pytest.approx(TARGET_MEAN, abs=1e-9)
    assert r.std(ddof=1) == pytest.approx(TARGET_STD, abs=1e-9)
    down = np.minimum(r - RF / 252.0, 0.0)
    assert np.sqrt(np.mean(down**2)) == pytest.approx(TARGET_DD_DEV, abs=1e-6)

    m = compute_metrics(r, rf_annual=RF)
    assert m.sharpe_ann == pytest.approx(2.99, abs=0.01)
    assert m.sortino_ann == pytest.approx(4.45, abs=0.02)
    assert m.n_days == 87


def test_counts_and_vami_identities() -> None:
    r = np.array([0.01, -0.005, 0.02, 0.0, -0.01])
    m = compute_metrics(r, rf_annual=0.0)
    assert m.pct_positive == pytest.approx(2 / 5)
    nav = 100_000.0 * np.cumprod(np.concatenate([[1.0], 1.0 + r]))
    np.testing.assert_allclose(daily_returns(nav), r, atol=1e-12)
    assert m.vami_final == pytest.approx(1000.0 * np.prod(1.0 + r))


def test_max_dd_dates_and_recovery() -> None:
    r = np.array([0.02, 0.01, -0.05, -0.06, 0.03, 0.09, 0.01])
    m = compute_metrics(r, rf_annual=0.0)
    # peak after day 2 (index 2 of VAMI incl. base), valley after day 4
    assert m.dd_peak_idx == 2
    assert m.dd_valley_idx == 4
    expected_dd = 1.0 - (0.95 * 0.94)
    assert m.max_dd == pytest.approx(expected_dd, abs=1e-12)
    assert m.recovery_days == 2  # +3% then +9% regains the prior peak
