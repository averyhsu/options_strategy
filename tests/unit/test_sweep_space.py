import numpy as np

from options_strategy.sweep.runner import prune_reasons
from options_strategy.sweep.space import (
    DIM_NAMES,
    params_from_unit,
    sobol_params,
    weekly_config,
)


def test_sobol_deterministic_and_in_bounds() -> None:
    a = sobol_params(64, seed=7)
    b = sobol_params(64, seed=7)
    assert a == b
    for p in a:
        assert 0.05 <= p["short_put_delta"] <= 0.50
        assert 0.05 <= p["short_call_delta"] <= 0.50
        assert 7 <= p["long_put_offset_days"] <= 56
        assert 0.0 <= p["long_strike_offset"] <= 100.0 and p["long_strike_offset"] % 5 == 0
        assert 0.20 <= p["credit_threshold_frac"] <= 0.60
        assert p["risk_fraction"] in (0.10, 0.15, 0.20)
        assert p["ema_len"] in (13, 21, 34)
        assert p["strike_family"] in ("percentile", "delta")
        assert 0.80 <= p["coverage_q_put"] <= 0.95
        assert 0.80 <= p["coverage_q_call"] <= 0.95


def test_every_param_maps_to_valid_weekly_config() -> None:
    for p in sobol_params(32, seed=11):
        cfg = weekly_config(p)
        assert cfg.entry.execution == "eod_mid"
        assert cfg.structure.strike_family == p["strike_family"]
        assert cfg.structure.band_ema_len == p["ema_len"]
        assert cfg.structure.coverage_q_put == p["coverage_q_put"]
        if p["defense"] == "none":
            assert cfg.defense.trigger == "none"
        else:
            assert (cfg.defense.trigger, cfg.defense.action) == (
                "close_beyond",
                "close_tested_side",
            )


def test_extreme_corners_map() -> None:
    lo = params_from_unit(np.zeros(len(DIM_NAMES)))
    hi = params_from_unit(np.full(len(DIM_NAMES), 0.999999))
    for p in (lo, hi):
        weekly_config(p)  # must validate


def _metrics(**over) -> dict:
    base = {
        "n_cycles": 400,
        "expectancy_per_cycle": 150.0,
        "weekly_wr": 0.85,
        "win_mag_median": 0.30,
        "max_dd": 0.12,
    }
    base.update(over)
    return base


def test_prune_rules_match_plan_9_1() -> None:
    assert prune_reasons(_metrics()) == []
    assert prune_reasons(_metrics(n_cycles=5)) == ["no_trades"]
    assert "expectancy" in prune_reasons(_metrics(expectancy_per_cycle=-1.0))
    assert "win_rate" in prune_reasons(_metrics(weekly_wr=0.5))
    assert "win_rate" in prune_reasons(_metrics(weekly_wr=0.99))
    assert "win_magnitude" in prune_reasons(_metrics(win_mag_median=0.05))
    assert "win_magnitude" in prune_reasons(_metrics(win_mag_median=float("nan")))
    assert "drawdown" in prune_reasons(_metrics(max_dd=0.55))
