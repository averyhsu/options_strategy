"""Sweep space over PLAN §8 priors: Sobol points in [0,1)^20 mapped to
WeeklyConfig instances (Track-A form: eod_mid execution, defense collapsed to
{none, close-side-EOD} per §9.1).

2026-08-10 amendment: `strike_family` is a dimension — "percentile" (the
DEFAULT family: short strikes at trailing above-EMA return quantiles, coverage
q_put/q_call in [0.80, 0.95]) vs "delta" (fallback). Delta dims are inert
under the percentile family and vice versa; those marginals are expected
plateaus and the ABC gate treats them as such.

2026-08-16 amendment (near-calendar evidence, PLAN §1.6): `wing_family` splits
the long_strike_offset prior — "near" (DEFAULT: 0-50 pts from the short,
0 = pure calendar) vs "wide" (fallback: 50-100 pts); `front_dte` in {7, 14}
(default 7) makes the front-leg DTE the small dial the author described.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy.stats import qmc

from options_strategy.strategy.defense import DefenseConfig
from options_strategy.strategy.diagonal import StructureConfig
from options_strategy.strategy.entry import EntryConfig
from options_strategy.strategy.regime import RegimeConfig
from options_strategy.strategy.weekly import SizingConfig, WeeklyConfig

THRESHOLD_REFS = ("width", "scenario_r", "max_gain")
REGIME_ACTIONS = ("trade_all", "bull_only", "retracement_only", "any_event")
EMA_LENS = (13, 21, 34)
HYSTERESIS = (0.0, 0.25, 0.5)
DEFENSES = ("none", "close_side_eod")
RISK_DEFS = ("scenario", "width", "margin")
RISK_FRACS = (0.10, 0.15, 0.20)
STRIKE_FAMILIES = ("percentile", "delta")
WING_FAMILIES = ("near", "wide")  # near = 0-50 pts (default), wide = 50-100 (fallback)
FRONT_DTES = (7, 14)
# front_dte -> (front_min_days, front_max_days) window for select_expiries
FRONT_DTE_WINDOWS = {7: (5, 9), 14: (12, 16)}

DIM_NAMES = [
    "short_put_delta",
    "short_call_delta",
    "long_put_offset_days",
    "long_call_offset_days",
    "long_strike_offset",
    "credit_threshold_frac",
    "threshold_reference",
    "require_credit",
    "min_credit_frac",
    "regime_action",
    "ema_len",
    "hysteresis",
    "defense",
    "risk_definition",
    "risk_fraction",
    "strike_family",
    "coverage_q_put",
    "coverage_q_call",
    "wing_family",
    "front_dte",
]


class SweepRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n_configs: int = 16384
    seed: int = 20260807
    world: str = "data/synthetic/worlds/p4-world-10y-synthetic"
    out_dir: str = "experiments/p4"


def _choice(u: float, options: tuple) -> object:
    return options[min(int(u * len(options)), len(options) - 1)]


def params_from_unit(u: np.ndarray) -> dict:
    """One Sobol point -> raw parameter dict (used for marginals + config)."""
    assert len(u) == len(DIM_NAMES)
    wing_family = _choice(u[18], WING_FAMILIES)
    # u[4] scales the offset WITHIN the wing family: near 0..50, wide 50..100
    offset = u[4] * 50.0 if wing_family == "near" else 50.0 + u[4] * 50.0
    return {
        "short_put_delta": 0.05 + u[0] * 0.45,
        "short_call_delta": 0.05 + u[1] * 0.45,
        "long_put_offset_days": 7 + int(u[2] * 50),  # 7..56
        "long_call_offset_days": 7 + int(u[3] * 50),
        "long_strike_offset": float(np.round(offset / 5) * 5),  # 5-pt steps
        "credit_threshold_frac": 0.20 + u[5] * 0.40,
        "threshold_reference": _choice(u[6], THRESHOLD_REFS),
        "require_credit": bool(_choice(u[7], (True, False))),
        "min_credit_frac": u[8] * 0.20,
        "regime_action": _choice(u[9], REGIME_ACTIONS),
        "ema_len": _choice(u[10], EMA_LENS),
        "hysteresis": _choice(u[11], HYSTERESIS),
        "defense": _choice(u[12], DEFENSES),
        "risk_definition": _choice(u[13], RISK_DEFS),
        "risk_fraction": _choice(u[14], RISK_FRACS),
        "strike_family": _choice(u[15], STRIKE_FAMILIES),
        "coverage_q_put": 0.80 + u[16] * 0.15,
        "coverage_q_call": 0.80 + u[17] * 0.15,
        "wing_family": wing_family,
        "front_dte": int(_choice(u[19], FRONT_DTES)),
    }


def weekly_config(params: dict) -> WeeklyConfig:
    defense = (
        DefenseConfig(trigger="none")
        if params["defense"] == "none"
        else DefenseConfig(trigger="close_beyond", timing="eod", action="close_tested_side")
    )
    return WeeklyConfig(
        structure=StructureConfig(
            strike_family=params["strike_family"],
            coverage_q_put=params["coverage_q_put"],
            coverage_q_call=params["coverage_q_call"],
            band_ema_len=params["ema_len"],
            short_put_delta=params["short_put_delta"],
            short_call_delta=params["short_call_delta"],
            long_put_expiry_offset_days=params["long_put_offset_days"],
            long_call_expiry_offset_days=params["long_call_offset_days"],
            long_strike_offset=params["long_strike_offset"],
            front_min_days=FRONT_DTE_WINDOWS[params["front_dte"]][0],
            front_max_days=FRONT_DTE_WINDOWS[params["front_dte"]][1],
            require_credit=params["require_credit"],
            min_credit_frac=params["min_credit_frac"],
        ),
        entry=EntryConfig(
            execution="eod_mid",
            credit_threshold_frac=params["credit_threshold_frac"],
            threshold_reference=params["threshold_reference"],
        ),
        sizing=SizingConfig(
            risk_definition=params["risk_definition"],
            risk_fraction=params["risk_fraction"],
        ),
        defense=defense,
        regime=RegimeConfig(ema_len=params["ema_len"], hysteresis_atr=params["hysteresis"]),
        regime_action=params["regime_action"],
        manage_t1="hold",
    )


def sobol_params(n: int, seed: int) -> list[dict]:
    sampler = qmc.Sobol(d=len(DIM_NAMES), scramble=True, seed=seed)
    m = int(np.ceil(np.log2(max(n, 2))))
    u = sampler.random_base2(m)[:n]
    return [params_from_unit(row) for row in u]
