import datetime as dt

from options_strategy.engine.fills import (
    LegQuote,
    combo_quote,
    evaluate_immediate,
    evaluate_resting,
)
from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.orders import ComboOrder, FillModel

EXP_FRONT = dt.date(2026, 3, 13)
EXP_BACK = dt.date(2026, 4, 2)

SC = OptionKey("SPXW", EXP_FRONT, 5100.0, "C")
SP = OptionKey("SPXW", EXP_FRONT, 4900.0, "P")
LC = OptionKey("SPXW", EXP_BACK, 5150.0, "C")
LP = OptionKey("SPXW", EXP_BACK, 4850.0, "P")

# Double diagonal: sell front strangle, buy back wings.
LEGS = ((SC, -1), (SP, -1), (LC, 1), (LP, 1))


def _quotes(width: float = 0.4) -> dict:
    h = width / 2
    return {
        SC: LegQuote(bid=10.0 - h, ask=10.0 + h, bid_size=40, ask_size=40, sane=True),
        SP: LegQuote(bid=12.0 - h, ask=12.0 + h, bid_size=40, ask_size=40, sane=True),
        LC: LegQuote(bid=8.0 - h, ask=8.0 + h, bid_size=40, ask_size=40, sane=True),
        LP: LegQuote(bid=9.0 - h, ask=9.0 + h, bid_size=40, ask_size=40, sane=True),
    }


def _order(limit: float | None, immediate: bool = False, qty: int = 4) -> ComboOrder:
    return ComboOrder(order_id=1, legs=LEGS, qty=qty, max_net_debit=limit, immediate=immediate)


def test_combo_quote_hand_computed() -> None:
    cq = combo_quote(_order(-4.0), _quotes(width=0.4))
    assert cq is not None
    # Selling at market: shorts hit bids (9.8 + 11.8), longs lift asks (8.2 + 9.2)
    # net debit = -(9.8 + 11.8) + 8.2 + 9.2 = -4.2 (a 4.2 credit).
    assert abs(cq.market_debit - (-4.2)) < 1e-12
    assert abs(cq.mid_debit - (-5.0)) < 1e-12
    assert abs(cq.half_spread - 0.8) < 1e-12  # 4 legs x 0.2
    assert cq.max_qty == 40


def test_combo_quote_refuses_flagged_or_one_sided_legs() -> None:
    q = _quotes()
    q[SC] = LegQuote(bid=9.8, ask=10.2, bid_size=40, ask_size=40, sane=False)
    assert combo_quote(_order(-4.0), q) is None
    q = _quotes()
    q[SP] = LegQuote(bid=0.0, ask=12.2, bid_size=0, ask_size=40, sane=True)
    assert combo_quote(_order(-4.0), q) is None  # selling a leg with no bid
    assert combo_quote(_order(-4.0), {k: v for k, v in _quotes().items() if k != LP}) is None


def test_conservative_needs_crossing_plus_one_full_bar() -> None:
    order = _order(limit=-4.2)  # credit target 4.2 == market credit right now
    cq = combo_quote(order, _quotes())
    d1 = evaluate_resting(order, cq, FillModel.CONSERVATIVE, 0.08, 0.25)
    assert d1 is None and order.crossed_bars == 1
    d2 = evaluate_resting(order, cq, FillModel.CONSERVATIVE, 0.08, 0.25)
    assert d2 is not None
    assert d2.price_debit == -4.2  # fills AT the limit
    assert d2.qty == 4  # min(remaining=4, 40 * 0.25)


def test_conservative_persistence_resets_when_uncrossed() -> None:
    order = _order(limit=-4.2)
    good = combo_quote(order, _quotes())
    worse = combo_quote(order, _quotes(width=1.2))  # market credit only 3.6
    assert evaluate_resting(order, good, FillModel.CONSERVATIVE, 0.08, 0.25) is None
    assert evaluate_resting(order, worse, FillModel.CONSERVATIVE, 0.08, 0.25) is None
    assert order.crossed_bars == 0
    assert evaluate_resting(order, good, FillModel.CONSERVATIVE, 0.08, 0.25) is None
    assert evaluate_resting(order, good, FillModel.CONSERVATIVE, 0.08, 0.25) is not None


def test_mid_model_needs_concession_cleared() -> None:
    # mid credit 5.0, half 0.8, k=0.5 -> achievable credit 4.6.
    order = _order(limit=-4.6)
    cq = combo_quote(order, _quotes())
    assert evaluate_resting(order, cq, FillModel.MID, 0.5, 0.25) is not None
    tighter = _order(limit=-4.61)
    assert evaluate_resting(tighter, cq, FillModel.MID, 0.5, 0.25) is None


def test_optimistic_fills_on_mid_touch() -> None:
    order = _order(limit=-5.0)
    cq = combo_quote(order, _quotes())
    d = evaluate_resting(order, cq, FillModel.OPTIMISTIC, 0.08, 0.25)
    assert d is not None and d.price_debit == -5.0
    assert evaluate_resting(_order(limit=-5.01), cq, FillModel.OPTIMISTIC, 0.08, 0.25) is None


def test_participation_cap_partials() -> None:
    order = _order(limit=-5.0, qty=100)
    cq = combo_quote(order, _quotes())  # max_qty 40, cap 0.25 -> 10 per bar
    d = evaluate_resting(order, cq, FillModel.OPTIMISTIC, 0.08, 0.25)
    assert d is not None and d.qty == 10
    order.filled_qty += d.qty
    d2 = evaluate_resting(order, cq, FillModel.OPTIMISTIC, 0.08, 0.25)
    assert d2 is not None and d2.qty == 10  # keeps working the book


def test_immediate_crosses_the_spread() -> None:
    order = _order(limit=None, immediate=True, qty=2)
    cq = combo_quote(order, _quotes())
    d = evaluate_immediate(order, cq, k_exit=1.0, participation_cap=0.25)
    assert d is not None
    # mid -5.0 plus full half-spread cross 0.8 -> pays -4.2 (gives up 0.8 credit)
    assert abs(d.price_debit - (-4.2)) < 1e-12
