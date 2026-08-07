"""Structural protocol for the broker as strategies see it (keeps strategy
modules free of engine/driver imports — invariant §11.2 grep-lint).
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.orders import ComboOrder


class BrokerLike(Protocol):
    orders: dict[int, ComboOrder]

    def submit(
        self,
        legs: tuple[tuple[OptionKey, int], ...],
        qty: int,
        max_net_debit: float | None,
        immediate: bool = False,
        good_until: dt.datetime | None = None,
    ) -> int: ...

    def cancel(self, order_id: int) -> None: ...
