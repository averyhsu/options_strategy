"""Track B event-driven backtest driver (PLAN §7.1).

Per session: AM settlements (SET at the open) -> bar loop (strategy sees only
MarketView; broker evaluates orders on the same snapshot) -> PM settlements
after the close print -> EOD marks and the conservation check. Daily NAV uses
the last RTH bar's marks (IBKR-like 4pm).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.data.qa import (
    QAConfig,
    _sanity_flags,  # same sanity layer as the QA gate
)
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.fills import (
    ComboQuote,
    combo_quote,
    evaluate_immediate,
    evaluate_resting,
)
from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.marketview import MarketView
from options_strategy.engine.marks import mark_positions
from options_strategy.engine.orders import ComboOrder, OrderState
from options_strategy.engine.portfolio import Portfolio
from options_strategy.pricing.settlement import SettlementTable


class Strategy(Protocol):
    def on_bar(self, view: MarketView, portfolio: Portfolio, broker: Broker) -> None: ...


class Broker:
    """Order book of the simulation. Strategies submit/cancel; the driver
    evaluates fills. No routing, no external side effects."""

    def __init__(self, cfg: EngineConfig, portfolio: Portfolio):
        self.cfg = cfg
        self.portfolio = portfolio
        self._next_id = 1
        self.orders: dict[int, ComboOrder] = {}

    def submit(
        self,
        legs: tuple[tuple[OptionKey, int], ...],
        qty: int,
        max_net_debit: float | None,
        immediate: bool = False,
        good_until: dt.datetime | None = None,
    ) -> int:
        order = ComboOrder(
            order_id=self._next_id,
            legs=legs,
            qty=qty,
            max_net_debit=max_net_debit,
            immediate=immediate,
            good_until=good_until,
        )
        order.validate()
        self.orders[order.order_id] = order
        self._next_id += 1
        return order.order_id

    def cancel(self, order_id: int) -> None:
        order = self.orders.get(order_id)
        if order is not None and order.state is OrderState.OPEN:
            order.state = OrderState.CANCELLED

    def open_orders(self) -> list[ComboOrder]:
        return [o for o in self.orders.values() if o.state is OrderState.OPEN]

    def evaluate(self, view: MarketView) -> None:
        quotes = view.quotes()
        for order in self.open_orders():
            if order.good_until is not None and view.ts > order.good_until:
                order.state = OrderState.EXPIRED
                continue
            cq = combo_quote(order, quotes)
            if cq is None:
                if not order.immediate:
                    order.crossed_bars = 0  # bad data breaks persistence
                continue
            decision = self._decide(order, cq)
            if decision is None:
                continue
            fees = self.cfg.fees.fill_fee(decision.qty, n_legs=len(order.legs))
            self.portfolio.apply_combo_fill(
                ts=view.ts,
                order_id=order.order_id,
                legs=order.legs,
                qty=decision.qty,
                price_debit=decision.price_debit,
                fees=fees,
            )
            order.filled_qty += decision.qty
            if order.remaining == 0:
                order.state = OrderState.FILLED

    def _decide(self, order: ComboOrder, cq: ComboQuote):
        if order.immediate:
            return evaluate_immediate(
                order, cq, self.cfg.exit_cross_fraction, self.cfg.participation_cap
            )
        return evaluate_resting(
            order, cq, self.cfg.fill_model, self.cfg.k_mid_concession, self.cfg.participation_cap
        )


@dataclass
class BacktestResult:
    daily: pl.DataFrame  # session, nav, cash, mtm, n_option_positions
    portfolio: Portfolio
    marks_history: list[dict] = field(default_factory=list)


def run_backtest(
    adapter: SyntheticWorldAdapter,
    strategy: Strategy,
    cfg: EngineConfig | None = None,
    initial_cash: float | None = None,
) -> BacktestResult:
    cfg = cfg or EngineConfig()
    portfolio = Portfolio(initial_cash if initial_cash is not None else cfg.account_size)
    broker = Broker(cfg, portfolio)
    settle_table = SettlementTable(adapter.settlements())
    forwards_all = adapter.forwards_extracted()
    flags_all = adapter.quality_flags()
    key_cols = ["ts", "root", "expiry_date", "strike", "cp"]

    underlying = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    sessions = adapter.sessions()
    expiries = adapter.expiries()

    daily_rows: list[dict] = []
    result = BacktestResult(daily=pl.DataFrame(), portfolio=portfolio)

    for session in sessions["session"].to_list():
        _settle(portfolio, settle_table, expiries, session, kind="AM")

        quotes_day = adapter.option_quotes(session)
        quotes_day = quotes_day.join(
            flags_all.select([*key_cols, "flags"]), on=key_cols, how="left"
        ).with_columns(pl.col("flags").fill_null(0))
        bars = underlying.filter(pl.col("session") == session)
        spot_by_ts = dict(zip(bars["ts"].to_list(), bars["close"].to_list(), strict=True))

        snap_ts = quotes_day["ts"].unique().sort().to_list()
        last_view: MarketView | None = None
        for i, ts in enumerate(snap_ts):
            chain = quotes_day.filter(pl.col("ts") == ts)
            fwd = forwards_all.filter(pl.col("ts") == ts)
            view = MarketView(
                ts=ts,
                spot=float(spot_by_ts[ts]),
                chain=chain,
                forwards=fwd,
                session_date=session,
                is_last_bar_of_session=(i == len(snap_ts) - 1),
            )
            strategy.on_bar(view, portfolio, broker)
            broker.evaluate(view)
            last_view = view

        _settle(portfolio, settle_table, expiries, session, kind="PM")

        if last_view is None:
            continue
        marks = mark_positions(portfolio, last_view)
        nav = portfolio.check_conservation(marks)
        daily_rows.append(
            {
                "session": session,
                "nav": nav,
                "cash": portfolio.cash,
                "mtm": nav - portfolio.cash,
                "n_option_positions": len(portfolio.option_positions()),
            }
        )
        result.marks_history.append({"session": session, "marks": marks})

    result.daily = pl.DataFrame(daily_rows)
    return result


def _settle(
    portfolio: Portfolio,
    table: SettlementTable,
    expiries: pl.DataFrame,
    session: dt.date,
    kind: str,
) -> None:
    todays = expiries.filter((pl.col("expiry_date") == session) & (pl.col("settlement") == kind))
    if todays.height == 0:
        return
    roots = set(todays["root"].to_list())
    for key in list(portfolio.option_positions()):
        if key.expiry == session and key.root in roots and key.settlement == kind:
            portfolio.settle_expiry(key, table.value(key.root, key.expiry))


def sanity_flag_frame(quotes_day: pl.DataFrame, qa_cfg: QAConfig | None = None) -> pl.DataFrame:
    """Convenience for tests: compute the QA sanity layer on a raw quotes frame."""
    return _sanity_flags(quotes_day, qa_cfg or QAConfig(), bar_minutes=1)
