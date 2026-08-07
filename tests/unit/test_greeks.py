import numpy as np
import pytest

from options_strategy.pricing.black76 import price as b76
from options_strategy.pricing.greeks import greeks

RF = 0.0262
CASES = [
    # (f, k, tau, sigma, cp)
    (5000.0, 5000.0, 30 / 365, 0.18, 1),
    (5000.0, 4800.0, 7 / 365, 0.22, -1),
    (5000.0, 5400.0, 0.25, 0.35, 1),
    (5000.0, 4500.0, 1.0, 0.15, -1),
]


@pytest.mark.parametrize("f,k,tau,sigma,cp", CASES)
def test_delta_gamma_vega_match_finite_differences(f, k, tau, sigma, cp) -> None:
    df = np.exp(-RF * tau)
    g = greeks(f, k, tau, sigma, df, cp=cp)

    h = f * 1e-5
    d_num = (b76(f + h, k, tau, sigma, df, cp=cp) - b76(f - h, k, tau, sigma, df, cp=cp)) / (2 * h)
    np.testing.assert_allclose(g.delta, d_num, rtol=1e-6, atol=1e-9)

    g_num = (
        b76(f + h, k, tau, sigma, df, cp=cp)
        - 2 * b76(f, k, tau, sigma, df, cp=cp)
        + b76(f - h, k, tau, sigma, df, cp=cp)
    ) / (h * h)
    np.testing.assert_allclose(g.gamma, g_num, rtol=1e-4, atol=1e-10)

    hv = 1e-6
    v_num = (b76(f, k, tau, sigma + hv, df, cp=cp) - b76(f, k, tau, sigma - hv, df, cp=cp)) / (
        2 * hv
    )
    np.testing.assert_allclose(g.vega, v_num, rtol=1e-6, atol=1e-8)


@pytest.mark.parametrize("f,k,tau,sigma,cp", CASES)
def test_theta_matches_calendar_derivative(f, k, tau, sigma, cp) -> None:
    """theta = dV/dt at fixed F, sigma with df = exp(-r*(T-t))."""
    g = greeks(f, k, tau, sigma, np.exp(-RF * tau), cp=cp)
    ht = 1e-6
    v_plus = b76(f, k, tau + ht, sigma, np.exp(-RF * (tau + ht)), cp=cp)
    v_minus = b76(f, k, tau - ht, sigma, np.exp(-RF * (tau - ht)), cp=cp)
    theta_num = -(v_plus - v_minus) / (2 * ht)
    np.testing.assert_allclose(g.theta, theta_num, rtol=1e-4, atol=1e-6)


def test_put_call_delta_relation_and_shared_gamma_vega() -> None:
    f, k, tau, sigma = 5000.0, 5100.0, 0.1, 0.2
    df = np.exp(-RF * tau)
    gc = greeks(f, k, tau, sigma, df, cp=1)
    gp = greeks(f, k, tau, sigma, df, cp=-1)
    np.testing.assert_allclose(gc.delta - gp.delta, df, rtol=1e-12)
    np.testing.assert_allclose(gc.gamma, gp.gamma, rtol=1e-12)
    np.testing.assert_allclose(gc.vega, gp.vega, rtol=1e-12)


def test_expired_greeks_are_flat() -> None:
    g = greeks(5000.0, 4900.0, 0.0, 0.3, 1.0, cp=1)
    assert g.gamma == 0.0 and g.vega == 0.0 and g.theta == 0.0
    assert g.delta == 1.0  # ITM call at expiry
