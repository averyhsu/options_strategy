"""The sweep's fast runner must reproduce run_track_a decision-for-decision on
EOD-expressible configs (extending the Track A == Track B chain to the sweep
engine), and its vectorized scenario grid must match the scalar one."""

import numpy as np
import pytest

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.margin import scenario_extremes
from options_strategy.engine.track_a import run_track_a
from options_strategy.strategy.defense import DefenseConfig
from options_strategy.strategy.diagonal import StructureConfig
from options_strategy.strategy.entry import EntryConfig
from options_strategy.strategy.weekly import SizingConfig, WeeklyConfig
from options_strategy.sweep.fast_runner import run_config, scenario_extremes_fast
from options_strategy.sweep.precompute import build_cache
from options_strategy.sweep.space import sobol_params, weekly_config

ENGINE = EngineConfig()


@pytest.fixture(scope="module")
def cache_and_adapter(clean_world, clean_world_qa):
    _, paths, _ = clean_world
    assert clean_world_qa.clean
    adapter = SyntheticWorldAdapter(paths.root)
    combos = [
        (13, 0.0),
        (21, 0.0),
        (21, 0.25),
        (21, 0.5),
        (34, 0.0),
        (13, 0.25),
        (13, 0.5),
        (34, 0.25),
        (34, 0.5),
    ]
    return build_cache(adapter, combos), adapter


def _trading_cfg() -> WeeklyConfig:
    return WeeklyConfig(
        structure=StructureConfig(
            strike_family="delta",
            short_put_delta=0.25,
            short_call_delta=0.20,
            long_put_expiry_offset_days=3,
            long_call_expiry_offset_days=3,
            long_strike_offset=25.0,
            min_credit_frac=0.0,
            require_credit=False,
        ),
        entry=EntryConfig(execution="eod_mid", credit_threshold_frac=0.05),
        sizing=SizingConfig(risk_fraction=0.15),
        defense=DefenseConfig(trigger="none"),
        regime_action="trade_all",
    )


def _compare(cache, adapter, cfg: WeeklyConfig) -> tuple[int, float]:
    fast = run_config(
        cache, cfg, ENGINE.account_size, ENGINE.fees.per_contract_leg, ENGINE.participation_cap
    )
    slow = run_track_a(adapter, cfg, ENGINE, initial_cash=ENGINE.account_size)
    nav_slow = slow.daily["nav"].to_numpy()
    assert len(fast.nav_daily) == len(nav_slow)
    np.testing.assert_allclose(fast.nav_daily, nav_slow, rtol=1e-9, atol=1e-4)
    assert fast.n_fills == len(slow.portfolio.fills)
    return fast.n_fills, float(fast.nav_daily[-1])


def test_fast_runner_matches_track_a_on_trading_config(cache_and_adapter) -> None:
    cache, adapter = cache_and_adapter
    n_fills, _ = _compare(cache, adapter, _trading_cfg())
    assert n_fills >= 2, "config must actually trade for this test to bite"


@pytest.fixture(scope="module")
def band_world_adapter(tmp_path_factory) -> SyntheticWorldAdapter:
    """~24-week EOD-only world: long enough for a real trailing band history
    (the 3-week tiny world can never complete a weekly EMA)."""
    import datetime as dt

    from options_strategy.data.qa import run_qa
    from options_strategy.data.synthetic.config import (
        ChainParams,
        SnapshotSpec,
        SyntheticWorldConfig,
    )
    from options_strategy.data.synthetic.world import generate_world

    root = tmp_path_factory.mktemp("bandworld")
    cfg = SyntheticWorldConfig(
        name="band-eod-synthetic",
        seed=17,
        start=dt.date(2025, 10, 6),
        end=dt.date(2026, 3, 20),
        chain=ChainParams(n_weeklies=8, n_monthlies=1, near_band_pct=0.02, span_pct=0.05),
        snapshots=SnapshotSpec(eod=True),
    )
    paths, _ = generate_world(cfg, root)
    assert run_qa(paths.root).clean
    return SyntheticWorldAdapter(paths.root)


def test_fast_runner_matches_track_a_on_percentile_family(band_world_adapter) -> None:
    """The §8.1 DEFAULT family must trade AND match Track A bit-for-bit.

    24 weeks is still too short for the production 21-week EMA + 52-obs
    warm-up, so the band parameters are scaled down (band_ema_len=4,
    min_band_obs=4) — this exercises the identical code path, not a relaxed
    tolerance."""
    from options_strategy.strategy.regime import RegimeConfig

    adapter = band_world_adapter
    cache = build_cache(adapter, [(4, 0.0)])
    cfg = WeeklyConfig(
        structure=StructureConfig(
            strike_family="percentile",
            coverage_q_put=0.85,
            coverage_q_call=0.85,
            band_ema_len=4,
            min_band_obs=4,
            long_put_expiry_offset_days=3,
            long_call_expiry_offset_days=3,
            long_strike_offset=25.0,
            min_credit_frac=0.0,
            require_credit=False,
        ),
        entry=EntryConfig(execution="eod_mid", credit_threshold_frac=0.05),
        sizing=SizingConfig(risk_fraction=0.15),
        defense=DefenseConfig(trigger="none"),
        regime=RegimeConfig(ema_len=4),
        regime_action="trade_all",
    )
    n_fills, _ = _compare(cache, adapter, cfg)
    assert n_fills >= 2, "percentile-family config must actually trade for this test to bite"


def test_fast_runner_matches_track_a_on_sobol_configs(cache_and_adapter) -> None:
    cache, adapter = cache_and_adapter
    traded = 0
    for params in sobol_params(6, seed=99):
        cfg = weekly_config(params)
        n_fills, _ = _compare(cache, adapter, cfg)
        traded += n_fills
    # most Sobol configs won't trade on the tiny world; equality must hold anyway


def test_vectorized_scenario_grid_matches_scalar() -> None:
    import datetime as dt

    from options_strategy.engine.instruments import OptionKey
    from options_strategy.engine.margin import LegState

    spot = 5000.0
    legs = [
        LegState(
            OptionKey("SPXW", dt.date(2026, 3, 13), 5100.0, "C"),
            -1,
            10.0,
            0.15,
            7 / 365,
            5001.0,
            0.999,
        ),
        LegState(
            OptionKey("SPXW", dt.date(2026, 3, 13), 4900.0, "P"),
            -1,
            12.0,
            0.20,
            7 / 365,
            5001.0,
            0.999,
        ),
        LegState(
            OptionKey("SPXW", dt.date(2026, 4, 2), 5150.0, "C"),
            1,
            28.0,
            0.16,
            27 / 365,
            5004.0,
            0.998,
        ),
        LegState(
            OptionKey("SPXW", dt.date(2026, 4, 2), 4850.0, "P"),
            1,
            34.0,
            0.21,
            27 / 365,
            5004.0,
            0.998,
        ),
    ]
    worst_s, best_s = scenario_extremes(legs, spot)
    worst_f, best_f = scenario_extremes_fast(legs, spot)
    assert worst_f == pytest.approx(worst_s, abs=1e-6)
    assert best_f == pytest.approx(best_s, abs=1e-6)
