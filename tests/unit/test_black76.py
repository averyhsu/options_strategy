import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from options_strategy.pricing.black76 import cp_sign, forward_intrinsic, price


def test_cp_sign_maps_strings_and_ints() -> None:
    assert cp_sign("C") == 1
    assert cp_sign("P") == -1
    np.testing.assert_array_equal(cp_sign(np.array(["C", "P", "C"])), [1, -1, 1])
    np.testing.assert_array_equal(cp_sign(np.array([1, -1])), [1, -1])


def test_put_call_parity_on_grid() -> None:
    f, df = 5000.0, 0.99
    strikes = np.arange(4000.0, 6001.0, 50.0)
    tau, sigma = 0.25, 0.2
    calls = price(f, strikes, tau, sigma, df, cp=1)
    puts = price(f, strikes, tau, sigma, df, cp=-1)
    np.testing.assert_allclose(calls - puts, df * (f - strikes), rtol=0, atol=1e-9)


def test_monotone_in_vol() -> None:
    sigmas = np.linspace(0.05, 1.5, 40)
    calls = price(5000.0, 5200.0, 0.1, sigmas, 1.0, cp=1)
    assert np.all(np.diff(calls) > 0)


def test_expiry_collapses_to_intrinsic() -> None:
    strikes = np.array([4500.0, 5000.0, 5500.0])
    got = price(5000.0, strikes, 0.0, 0.3, 1.0, cp=1)
    np.testing.assert_allclose(got, [500.0, 0.0, 0.0], atol=1e-12)
    got_p = price(5000.0, strikes, 0.0, 0.3, 0.98, cp=-1)
    np.testing.assert_allclose(got_p, [0.0, 0.0, 0.98 * 500.0], atol=1e-12)


def test_zero_vol_is_discounted_forward_intrinsic() -> None:
    got = price(5100.0, 5000.0, 0.5, 0.0, 0.97, cp=1)
    np.testing.assert_allclose(got, 0.97 * 100.0, atol=1e-12)


@settings(max_examples=300, deadline=None)
@given(
    f=st.floats(1000.0, 9000.0),
    k=st.floats(1000.0, 9000.0),
    tau=st.floats(0.0, 2.0),
    sigma=st.floats(0.0, 2.5),
    cp=st.sampled_from([1, -1]),
)
def test_price_within_no_arb_bounds(f: float, k: float, tau: float, sigma: float, cp: int) -> None:
    df = 0.98
    p = float(price(f, k, tau, sigma, df, cp=cp))
    lower = float(forward_intrinsic(f, k, df, cp=cp))
    upper = df * (f if cp == 1 else k)
    assert p >= lower - 1e-9
    assert p <= upper + 1e-9
