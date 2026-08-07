"""Engine golden strategies (invariants §11.6a/6b, §11.1, §11.7) on the tiny
clean world. The adapter refuses un-QA'd data, so these depend on the QA
fixture having produced quality flags and forwards.
"""

import numpy as np
import polars as pl
import pytest

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import run_backtest
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.instruments import OptionKey
from options_strategy.ledger import LedgerRow


@pytest.fixture(scope="module")
def adapter(clean_world, clean_world_qa) -> SyntheticWorldAdapter:
    _, paths, _ = clean_world
    assert clean_world_qa.clean
    return SyntheticWorldAdapter(paths.root)


class BuyHoldIndex:
    """Golden 6a: NAV must equal index total return exactly."""

    units = 10.0

    def __init__(self) -> None:
        self.entry_spot: float | None = None

    def on_bar(self, view, portfolio, broker) -> None:
        if self.entry_spot is None:
            self.entry_spot = view.spot
            portfolio.trade_index(self.units, view.spot)


class ShortPutToExpiry:
    """Golden 6b: sell one OTM front put immediately, hold to settlement."""

    def __init__(self) -> None:
        self.key: OptionKey | None = None
        self.order_id: int | None = None

    def on_bar(self, view, portfolio, broker) -> None:
        if self.order_id is not None:
            return
        front = min((e for e in view.expiries() if e[0] > view.session_date), key=lambda e: e[0])
        expiry, root, _ = front
        candidates = (
            view.chain(root=root, expiry=expiry)
            .filter((pl.col("cp") == "P") & (pl.col("bid") >= 1.0))
            .filter(pl.col("strike") < view.spot * 0.99)
            .sort("strike", descending=True)
        )
        if candidates.height == 0:
            return
        strike = candidates["strike"][0]
        self.key = OptionKey(root, expiry, strike, "P")
        self.order_id = broker.submit(
            legs=((self.key, -1),), qty=1, max_net_debit=None, immediate=True
        )


def test_golden_6a_buy_and_hold_index_equals_index_return(adapter) -> None:
    strat = BuyHoldIndex()
    result = run_backtest(adapter, strat, EngineConfig(), initial_cash=100_000.0)
    bars = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    daily_close = bars.group_by("session", maintain_order=True).agg(
        pl.col("close").last().alias("close")
    )
    joined = result.daily.join(daily_close, on="session")
    expected = 100_000.0 + strat.units * (joined["close"] - strat.entry_spot)
    np.testing.assert_allclose(joined["nav"].to_numpy(), expected.to_numpy(), atol=1e-6)


def test_golden_6b_short_put_pnl_is_credit_minus_intrinsic_minus_fees(adapter) -> None:
    strat = ShortPutToExpiry()
    result = run_backtest(adapter, strat, EngineConfig(), initial_cash=100_000.0)
    p = result.portfolio
    assert len(p.fills) == 1, "expected exactly one fill"
    fill = p.fills[0]
    assert fill.qty == 1 and fill.price_debit < 0  # a credit
    assert len(p.settlements) == 1, "the put must have settled"
    s = p.settlements[0]
    credit_cash = -fill.price_debit * 100.0
    expected_final = 100_000.0 + credit_cash - s.intrinsic * 100.0 - fill.fees
    assert abs(fill.fees - 1.60) < 1e-12
    assert not p.positions, "book must be flat after settlement"
    assert abs(p.cash - expected_final) < 1e-9
    final_nav = result.daily["nav"][-1]
    assert abs(final_nav - expected_final) < 1e-9


def test_invariant_7_determinism_identical_ledger_row_hash(adapter) -> None:
    def run() -> tuple[pl.DataFrame, str]:
        result = run_backtest(adapter, ShortPutToExpiry(), EngineConfig(), 100_000.0)
        row = LedgerRow(
            kind="backtest",
            config_hash="test",
            git_sha="test",
            data_version=adapter.data_version,
            seed=0,
            metrics={"final_nav": result.daily["nav"][-1], "n_fills": len(result.portfolio.fills)},
        )
        return result.daily, row.row_hash

    daily_a, hash_a = run()
    daily_b, hash_b = run()
    assert hash_a == hash_b
    assert daily_a.equals(daily_b)


def test_invariant_1_conservation_holds_every_session(adapter) -> None:
    # run_backtest calls check_conservation at every EOD mark; reaching the end
    # without EngineInvariantError IS the check. Assert it produced marks daily.
    result = run_backtest(adapter, ShortPutToExpiry(), EngineConfig(), 100_000.0)
    assert result.daily.height == adapter.sessions().height
    assert result.daily["nav"].is_finite().all()
