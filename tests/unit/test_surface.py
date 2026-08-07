import numpy as np
import pytest

from options_strategy.data.synthetic.config import HestonParams, SurfaceParams
from options_strategy.data.synthetic.surface import (
    expected_total_variance,
    implied_vol,
    ssvi_total_variance,
    validate_no_butterfly,
)

H = HestonParams()
P = SurfaceParams()


def test_expected_total_variance_limits() -> None:
    # At v_t = theta the expectation is exactly theta * tau.
    tau = np.array([0.01, 0.1, 1.0])
    np.testing.assert_allclose(expected_total_variance(H.theta, tau, H), H.theta * tau)
    # Above theta it decays toward theta*tau from above.
    w_hi = expected_total_variance(0.09, tau, H)
    assert np.all(w_hi > H.theta * tau)


def test_total_variance_increases_with_tenor_fixed_k() -> None:
    taus = np.linspace(1 / 365, 1.0, 60)
    for v_t in (0.01, 0.03, 0.09):
        theta_t = expected_total_variance(v_t, taus, H)
        for k in (-0.2, -0.05, 0.0, 0.05, 0.2):
            w = ssvi_total_variance(k, theta_t, P)
            assert np.all(np.diff(w) > 0), f"calendar violated at v_t={v_t}, k={k}"


def test_negative_rho_makes_put_wing_richer() -> None:
    theta_t = expected_total_variance(0.03, 30 / 365, H)
    iv_put_wing = implied_vol(-0.1, 30 / 365, theta_t, P)
    iv_call_wing = implied_vol(+0.1, 30 / 365, theta_t, P)
    assert iv_put_wing > iv_call_wing


def test_ivs_positive_and_finite_across_grid() -> None:
    taus = np.array([2 / 365, 7 / 365, 30 / 365, 90 / 365])
    ks = np.linspace(-0.5, 0.5, 101)
    for tau in taus:
        theta_t = float(expected_total_variance(0.03, tau, H))
        ivs = implied_vol(ks, tau, np.full_like(ks, theta_t), P)
        assert np.all(np.isfinite(ivs))
        assert np.all(ivs > 0)


def test_no_butterfly_validation_accepts_defaults_rejects_extremes() -> None:
    theta_lo = float(expected_total_variance(0.005, 1 / 365, H))
    theta_hi = float(expected_total_variance(0.5, 1.0, H))
    validate_no_butterfly(P, theta_lo, theta_hi)
    with pytest.raises(ValueError, match="butterfly"):
        validate_no_butterfly(SurfaceParams(eta=6.0), theta_lo, theta_hi)
    with pytest.raises(ValueError):
        validate_no_butterfly(SurfaceParams(gamma_=1.5), theta_lo, theta_hi)
