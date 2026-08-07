"""Fee model (PLAN §7.3): per contract per leg, component-split so the user
can true-up against a real IBKR statement. Default sums to ~$1.60/leg all-in
(the author's stated number) — see configs/base.yaml.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FeeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commission_per_leg: float = 0.65
    exchange_fee_per_leg: float = 0.65
    clearing_per_leg: float = 0.10
    regulatory_per_leg: float = 0.20
    multiplier: float = 1.0  # fee sensitivity x1..x3 in evaluation (PLAN §10.6)

    @property
    def per_contract_leg(self) -> float:
        base = (
            self.commission_per_leg
            + self.exchange_fee_per_leg
            + self.clearing_per_leg
            + self.regulatory_per_leg
        )
        return base * self.multiplier

    def fill_fee(self, n_contracts: int, n_legs: int = 1) -> float:
        """Total dollars for a fill of n_contracts on n_legs legs."""
        return self.per_contract_leg * abs(n_contracts) * n_legs
