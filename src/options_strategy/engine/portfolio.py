"""Portfolio & cash accounting (PLAN §7.4).

Invariant §11.1: cash + sum(position MTM) = NAV at every mark, and
final NAV = initial + trade cash + settlement cash - fees, reconciled from the
fill/settlement records (not just tracked state) so drift raises loudly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from options_strategy.engine import CONTRACT_MULTIPLIER
from options_strategy.engine.instruments import INDEX, IndexUnit, Instrument, OptionKey


class EngineInvariantError(AssertionError):
    pass


@dataclass(frozen=True)
class FillRecord:
    ts: dt.datetime
    order_id: int
    legs: tuple[tuple[OptionKey, int], ...]
    qty: int
    price_debit: float  # per combo, index points
    fees: float  # dollars
    cash_delta: float  # dollars, ex-fees


@dataclass(frozen=True)
class SettlementRecord:
    key: OptionKey
    qty: float
    settle_value: float
    intrinsic: float  # index points per contract
    cash_delta: float  # dollars


@dataclass
class Portfolio:
    initial_cash: float
    cash: float = field(init=False)
    positions: dict[Instrument, float] = field(default_factory=dict)
    fees_paid: float = 0.0
    trade_cash: float = 0.0
    settle_cash: float = 0.0
    fills: list[FillRecord] = field(default_factory=list)
    settlements: list[SettlementRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def _bump(self, inst: Instrument, delta: float) -> None:
        new = self.positions.get(inst, 0.0) + delta
        if abs(new) < 1e-12:
            self.positions.pop(inst, None)
        else:
            self.positions[inst] = new

    def apply_combo_fill(
        self,
        ts: dt.datetime,
        order_id: int,
        legs: tuple[tuple[OptionKey, int], ...],
        qty: int,
        price_debit: float,
        fees: float,
    ) -> None:
        cash_delta = -price_debit * qty * CONTRACT_MULTIPLIER
        self.cash += cash_delta - fees
        self.trade_cash += cash_delta
        self.fees_paid += fees
        for key, ratio in legs:
            self._bump(key, ratio * qty)
        self.fills.append(
            FillRecord(
                ts=ts,
                order_id=order_id,
                legs=legs,
                qty=qty,
                price_debit=price_debit,
                fees=fees,
                cash_delta=cash_delta,
            )
        )

    def trade_index(self, units: float, price: float) -> None:
        """Frictionless synthetic index unit (golden tests, delta hedge)."""
        self.cash -= units * price
        self.trade_cash -= units * price
        self._bump(INDEX, units)

    def settle_expiry(self, key: OptionKey, settle_value: float) -> None:
        qty = self.positions.pop(key, 0.0)
        if qty == 0.0:
            return
        w = 1.0 if key.cp == "C" else -1.0
        intrinsic = max(w * (settle_value - key.strike), 0.0)
        cash_delta = intrinsic * qty * CONTRACT_MULTIPLIER
        self.cash += cash_delta
        self.settle_cash += cash_delta
        self.settlements.append(
            SettlementRecord(
                key=key,
                qty=qty,
                settle_value=settle_value,
                intrinsic=intrinsic,
                cash_delta=cash_delta,
            )
        )

    def option_positions(self) -> dict[OptionKey, float]:
        return {k: q for k, q in self.positions.items() if isinstance(k, OptionKey)}

    def mtm(self, marks: dict[Instrument, float]) -> float:
        total = 0.0
        for inst, qty in self.positions.items():
            if inst not in marks:
                raise EngineInvariantError(f"no mark for open position {inst}")
            mult = 1.0 if isinstance(inst, IndexUnit) else CONTRACT_MULTIPLIER
            total += qty * marks[inst] * mult
        return total

    def nav(self, marks: dict[Instrument, float]) -> float:
        return self.cash + self.mtm(marks)

    def check_conservation(self, marks: dict[Instrument, float]) -> float:
        """Raises unless NAV reconciles from records; returns NAV."""
        nav = self.nav(marks)
        cash_recon = self.initial_cash + self.trade_cash + self.settle_cash - self.fees_paid
        if abs(cash_recon - self.cash) > 1e-6:
            raise EngineInvariantError(f"cash {self.cash:.6f} != reconstruction {cash_recon:.6f}")
        if abs(sum(s.cash_delta for s in self.settlements) - self.settle_cash) > 1e-6:
            raise EngineInvariantError("settlement records do not sum to settle_cash")
        if abs(sum(f.fees for f in self.fills) - self.fees_paid) > 1e-6:
            raise EngineInvariantError("fill records do not sum to fees_paid")
        return nav
