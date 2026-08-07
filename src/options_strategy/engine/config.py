"""Engine configuration, loaded from configs/base.yaml (PLAN §3.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from options_strategy.engine.fees import FeeConfig
from options_strategy.engine.orders import FillModel


class EngineConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fees: FeeConfig = FeeConfig()
    fill_model: FillModel = FillModel.CONSERVATIVE
    k_mid_concession: float = 0.08  # MID model: concession x combo half-spread
    exit_cross_fraction: float = 1.0  # k_exit: immediate orders cross this much
    participation_cap: float = 0.25
    rf_source: str = "synthetic"
    account_size: float = 100_000.0
