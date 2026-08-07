import numpy as np

from options_strategy.data.synthetic.config import MicrostructureParams
from options_strategy.data.synthetic.microstructure import (
    is_on_tick,
    make_quotes,
    snap_to_tick,
    tick_size,
)

MP = MicrostructureParams()


def test_tick_size_bands() -> None:
    np.testing.assert_array_equal(
        tick_size([0.05, 2.95, 3.0, 3.05, 100.0]), [0.05, 0.05, 0.10, 0.10, 0.10]
    )


def test_snap_is_band_consistent_at_the_boundary() -> None:
    # Ceiling 2.98 with the low tick gives 3.00, which sits in the high band —
    # still on-grid. 3.02 must ceil to 3.10, not 3.05.
    assert snap_to_tick(2.98, +1) == 3.00
    assert snap_to_tick(3.02, +1) == 3.10
    assert snap_to_tick(3.02, -1) == 3.00
    assert snap_to_tick(2.93, -1) == 2.90
    assert snap_to_tick(0.02, -1) == 0.0


def test_snap_results_are_on_tick() -> None:
    rng = np.random.default_rng(0)
    prices = rng.uniform(0.0, 50.0, 5000)
    assert np.all(is_on_tick(snap_to_tick(prices, +1)))
    assert np.all(is_on_tick(snap_to_tick(prices, -1)))


def test_quotes_sane_across_moneyness() -> None:
    rng = np.random.default_rng(1)
    mid = np.array([0.10, 0.45, 1.20, 3.10, 12.0, 55.0, 140.0])
    k_norm = np.array([3.0, 2.0, 1.2, 0.8, 0.4, 0.1, 0.0])
    q = make_quotes(mid, k_norm, 1.0, MP, rng)
    assert np.all(q.ask > q.bid)
    assert np.all(q.bid >= 0.0)
    assert np.all(is_on_tick(q.bid))
    assert np.all(is_on_tick(q.ask))
    assert np.all(q.ask_size >= 1)
    assert np.all(q.bid_size[q.bid > 0] >= 1)
    assert np.all(q.bid_size[q.bid == 0.0] == 0)


def test_stress_widens_spreads() -> None:
    rng = np.random.default_rng(2)
    mid = np.full(200, 25.0)
    k = np.zeros(200)
    calm = make_quotes(mid, k, 1.0, MP, np.random.default_rng(3))
    stressed = make_quotes(mid, k, 3.0, MP, rng)
    assert (stressed.ask - stressed.bid).mean() > (calm.ask - calm.bid).mean() * 2
