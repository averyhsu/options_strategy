"""Fill logic (PLAN §7.2) — the critical component.

Combo NBBO composes from leg NBBOs over SANE quotes only (quality-flagged or
one-sided legs block evaluation entirely: the backtest never fills against bad
data). Resting-order models, all filling AT the limit:

- CONSERVATIVE: executable-at-market net debit <= limit for a second
  consecutive bar (crossed through and persisted one full bar). Lower bound.
- MID: mid-based net debit plus a concession of k_mid * combo half-spread
  clears the limit. Central case; k_mid calibrated in evaluation to the
  author's $5-10/spread slippage.
- OPTIMISTIC: mid touches the limit momentarily. Upper bound only.

Immediate (defensive/closing) orders fill now at mid + k_exit * half-spread
against each leg. Fill size is capped by displayed size x participation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.orders import ComboOrder, FillModel

# Price comparisons tolerate 1e-9 index points (1e-7 cents, vs a $0.05 tick):
# whether a limit "touches" must not depend on float-summation association.
_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class LegQuote:
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    sane: bool


@dataclass(frozen=True)
class ComboQuote:
    """Signed-combo pricing in net-debit terms."""

    market_debit: float  # cost to execute NOW crossing spreads (buy@ask, sell@bid)
    mid_debit: float
    half_spread: float  # sum(|ratio| * leg half-spread)
    max_qty: int  # displayed-size cap BEFORE participation factor

    @property
    def two_sided(self) -> bool:
        return self.max_qty > 0


def combo_quote(order: ComboOrder, quotes: Mapping[OptionKey, LegQuote]) -> ComboQuote | None:
    """None if any leg is missing, flagged, or effectively one-sided."""
    market = 0.0
    mid = 0.0
    half = 0.0
    max_qty = 10**9
    for key, ratio in order.legs:
        q = quotes.get(key)
        if q is None or not q.sane:
            return None
        if ratio > 0:
            if q.ask <= 0:
                return None
            market += ratio * q.ask
            size = q.ask_size
        else:
            if q.bid <= 0 or q.bid_size <= 0:
                return None
            market += ratio * q.bid
            size = q.bid_size
        # leg mid computed exactly as strategy-side plans do — ratio * ((b+a)/2),
        # NOT (ratio*(b+a))/2 — so a limit placed AT the current mid compares
        # bit-identically (1-ULP associativity differences broke that once).
        leg_mid = (q.bid + q.ask) / 2.0
        leg_half = (q.ask - q.bid) / 2.0
        mid += ratio * leg_mid
        half += abs(ratio) * leg_half
        max_qty = min(max_qty, size // abs(ratio))
    return ComboQuote(market_debit=market, mid_debit=mid, half_spread=half, max_qty=int(max_qty))


@dataclass(frozen=True)
class FillDecision:
    qty: int
    price_debit: float  # net debit per combo actually paid (credit if negative)


def evaluate_resting(
    order: ComboOrder,
    cq: ComboQuote,
    model: FillModel,
    k_mid: float,
    participation_cap: float,
) -> FillDecision | None:
    """Mutates order.crossed_bars (persistence state); returns a fill or None."""
    assert order.max_net_debit is not None
    limit = order.max_net_debit

    if model is FillModel.CONSERVATIVE:
        crossed = cq.market_debit <= limit + _PRICE_EPS
        if crossed:
            order.crossed_bars += 1
        else:
            order.crossed_bars = 0
        if order.crossed_bars < 2:
            return None
    elif model is FillModel.MID:
        if not (cq.mid_debit + k_mid * cq.half_spread <= limit + _PRICE_EPS):
            return None
    elif model is FillModel.OPTIMISTIC:
        if not (cq.mid_debit <= limit + _PRICE_EPS):
            return None
    else:  # pragma: no cover - enum is closed
        raise ValueError(model)

    qty = min(order.remaining, _capped_qty(cq, participation_cap))
    if qty <= 0:
        return None
    return FillDecision(qty=qty, price_debit=limit)


def evaluate_immediate(
    order: ComboOrder, cq: ComboQuote, k_exit: float, participation_cap: float
) -> FillDecision | None:
    qty = min(order.remaining, _capped_qty(cq, participation_cap))
    if qty <= 0:
        return None
    return FillDecision(qty=qty, price_debit=cq.mid_debit + k_exit * cq.half_spread)


def _capped_qty(cq: ComboQuote, participation_cap: float) -> int:
    return int(cq.max_qty * participation_cap)
