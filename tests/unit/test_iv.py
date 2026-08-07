import numpy as np

from options_strategy.pricing.black76 import price as b76
from options_strategy.pricing.iv import implied_vol

RF = 0.0262


def _grid():
    f = 5000.0
    k = f * np.linspace(0.70, 1.30, 25)
    tau = np.array([1 / 365, 7 / 365, 30 / 365, 0.25, 1.0])
    sigma = np.array([0.08, 0.15, 0.30, 0.60, 1.20])
    kk, tt, ss = np.meshgrid(k, tau, sigma, indexing="ij")
    return f, kk.ravel(), tt.ravel(), ss.ravel()


def _otm_fwd_price(p: np.ndarray, f: float, k: np.ndarray, df: np.ndarray, cp: int) -> np.ndarray:
    """Undiscounted price of the parity-rotated OTM option (its information content)."""
    return (p - df * np.maximum(cp * (f - k), 0.0)) / df


def test_round_trip_within_1e6_across_grid() -> None:
    """PLAN §6 acceptance: |price(iv(p)) - p| <= 1e-6 across strike/DTE/vol grid."""
    f, k, t, s = _grid()
    for cp in (1, -1):
        df = np.exp(-RF * t)
        p = b76(f, k, t, s, df, cp=cp)
        iv_hat = implied_vol(p, f, k, t, df, cp=cp)
        otm = _otm_fwd_price(p, f, k, df, cp)
        # Every meaningful premium solves; numerically-zero wings refuse (NaN):
        assert np.all(np.isfinite(iv_hat[otm > 1e-8]))
        assert np.all(np.isnan(iv_hat[otm <= 1e-12]))
        solvable = np.isfinite(iv_hat)
        assert solvable.sum() > 500
        p_rt = b76(f, k[solvable], t[solvable], iv_hat[solvable], df[solvable], cp=cp)
        err = np.abs(p_rt - p[solvable])
        assert err.max() <= 1e-6, f"max round-trip err {err.max():.2e}"


def test_recovers_true_sigma_where_premium_lives() -> None:
    f, k, t, s = _grid()
    df = np.exp(-RF * t)
    for cp in (1, -1):
        p = b76(f, k, t, s, df, cp=cp)
        iv_hat = implied_vol(p, f, k, t, df, cp=cp)
        liquid = np.isfinite(iv_hat) & (_otm_fwd_price(p, f, k, df, cp) > 0.5)
        assert liquid.sum() > 300
        assert np.abs(iv_hat[liquid] - s[liquid]).max() < 1e-4


def test_deep_itm_rotation() -> None:
    f, k, tau, sigma, df = 5000.0, 3000.0, 0.25, 0.30, np.exp(-RF * 0.25)
    p = float(b76(f, k, tau, sigma, df, cp=1))
    iv_hat = float(implied_vol(p, f, k, tau, df, cp=1))
    assert abs(iv_hat - sigma) < 1e-4
    p_rt = float(b76(f, k, tau, iv_hat, df, cp=1))
    assert abs(p_rt - p) <= 1e-6


def test_out_of_band_prices_are_nan() -> None:
    f, k, tau, df = 5000.0, 5200.0, 0.1, 0.99
    below = df * 0.0  # call below intrinsic (OTM intrinsic is 0) -> exactly at bound
    assert np.isnan(implied_vol(below, f, k, tau, df, cp=1))
    above = df * f * 1.01  # above the call upper bound
    assert np.isnan(implied_vol(above, f, k, tau, df, cp=1))
    assert np.isnan(implied_vol(10.0, f, k, 0.0, df, cp=1))  # expired


def test_put_and_call_rotation_consistency() -> None:
    f, tau, sigma, df = 5000.0, 30 / 365, 0.22, np.exp(-RF * 30 / 365)
    strikes = np.array([4300.0, 4800.0, 5000.0, 5200.0, 5700.0])
    pc = b76(f, strikes, tau, sigma, df, cp=1)
    pp = b76(f, strikes, tau, sigma, df, cp=-1)
    iv_c = implied_vol(pc, f, strikes, tau, df, cp=1)
    iv_p = implied_vol(pp, f, strikes, tau, df, cp=-1)
    np.testing.assert_allclose(iv_c, iv_p, atol=1e-5)
    np.testing.assert_allclose(iv_c, sigma, atol=1e-5)
