"""Orders (PLAN §7.2): market/limit single- and multi-leg combos, including
resting GTC-intra-week combo limits with cancel/replace.

Price convention: a combo leg is (OptionKey, ratio) with ratio > 0 = buy,
ratio < 0 = sell, per 1 combo. All limits are NET DEBIT per combo in index
points — a credit order carries a negative max_net_debit (credit c* <=>
max_net_debit = -c*). One rule prices everything; no per-side special cases.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from options_strategy.engine.instruments import OptionKey


class FillModel(StrEnum):
    CONSERVATIVE = "conservative"
    MID = "mid"
    OPTIMISTIC = "optimistic"


class OrderState(StrEnum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class ComboOrder:
    order_id: int
    legs: tuple[tuple[OptionKey, int], ...]  # (key, signed ratio per combo)
    qty: int  # combos requested (> 0)
    max_net_debit: float | None  # None => immediate order at the exit rule
    immediate: bool = False  # True: exit/defensive order, fills now at cross rule
    good_until: dt.datetime | None = None  # resting orders expire here (GTC intra-week)
    state: OrderState = OrderState.OPEN
    filled_qty: int = 0
    # CONSERVATIVE persistence state: bar count the market has crossed through
    # the limit (fill requires >= 2 consecutive crossed bars: "persists >= 1
    # full bar" after the crossing bar).
    crossed_bars: int = field(default=0)

    @property
    def remaining(self) -> int:
        return self.qty - self.filled_qty

    def validate(self) -> None:
        if self.qty <= 0:
            raise ValueError("order qty must be positive")
        if not self.legs:
            raise ValueError("order needs legs")
        if not self.immediate and self.max_net_debit is None:
            raise ValueError("resting orders need a max_net_debit limit")
