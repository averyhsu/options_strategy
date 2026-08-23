"""The weekly SPX double-diagonal strategy (PLAN §8): regime-gated entries via
resting EV-gated ladders on the entry session, defense policy while holding,
optional T-1 management, settlement by the engine.

Cadence is Friday-to-Friday: a new cycle may be entered on the same session
the old front legs expire, so more than one cycle can be live on that day —
cycles are tracked as a list and retired the session after their front expiry.

Strategy code touches markets only through MarketView and BrokerLike.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from options_strategy.engine.broker_protocol import BrokerLike
from options_strategy.engine.margin import (
    contracts_for_risk,
    r_margin,
    r_scenario,
    r_width,
    scenario_extremes,
)
from options_strategy.engine.marketview import MarketView
from options_strategy.engine.portfolio import Portfolio
from options_strategy.strategy import defense as dfs
from options_strategy.strategy.defense import DefenseConfig
from options_strategy.strategy.diagonal import DiagonalPlan, StructureConfig, build_diagonal
from options_strategy.strategy.entry import (
    EntryConfig,
    in_entry_window,
    reference_points,
    rung_credit_thresholds,
    split_quantity,
    window_end,
)
from options_strategy.strategy.regime import RegimeConfig, regime_frame

REGIME_ACTIONS = ("trade_all", "bull_only", "retracement_only", "any_event")
T1_MODES = ("hold", "close_all")


class SizingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_definition: str = "scenario"  # scenario | width | margin
    risk_fraction: float = 0.15
    max_contracts: int = 200  # hard cap against degenerate R


class WeeklyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    structure: StructureConfig = StructureConfig()
    entry: EntryConfig = EntryConfig()
    sizing: SizingConfig = SizingConfig()
    defense: DefenseConfig = DefenseConfig()
    regime: RegimeConfig = RegimeConfig()
    regime_action: str = "trade_all"
    manage_t1: str = "hold"
    # Early exit (PLAN §8.2 / 2026-08-18 amendment): close the whole cycle at
    # EOD of the first session AFTER entry with (front_expiry - session).days
    # <= exit_dte, freeing that same session's entry (weekly cadence on 14d
    # fronts). None = hold to front expiry. Degenerate for 7d fronts, so the
    # sweep maps exit_mode to None there (inert dim).
    exit_dte: int | None = None

    def model_post_init(self, __context) -> None:
        if self.regime_action not in REGIME_ACTIONS:
            raise ValueError(f"regime_action {self.regime_action!r} not in {REGIME_ACTIONS}")
        if self.manage_t1 not in T1_MODES:
            raise ValueError(f"manage_t1 {self.manage_t1!r} not in {T1_MODES}")


@dataclass
class CycleState:
    entry_session: dt.date
    plan: DiagonalPlan
    r_dollars: float
    qty_target: int
    order_ids: list[int] = field(default_factory=list)
    entry_fills: int = 0
    entry_credit_points: float = 0.0  # qty-weighted total credit received
    relaxed: bool = False
    tested_memory: str | None = None
    defended_sides: set[str] = field(default_factory=set)
    harvested: bool = False
    t1_done: bool = False
    hedge_units: float = 0.0

    @property
    def front_expiry(self) -> dt.date:
        return self.plan.short_put.expiry


class DoubleDiagonalWeekly:
    def __init__(self, cfg: WeeklyConfig):
        self.cfg = cfg
        self.cycles: list[CycleState] = []
        self.defense_log: list[dict] = []
        self.week_log: list[dict] = []
        self._entry_sessions_handled: set[dt.date] = set()

    # ------------------------------------------------------------- entry --
    def _is_entry_session(self, view: MarketView) -> bool:
        return view.session_date.weekday() == 4 or view.is_last_session_of_week

    def _regime_allows(self, view: MarketView) -> tuple[bool, str, str]:
        hist = view.daily_history()
        if hist.height == 0:
            return True, "warmup", "none"
        frame = regime_frame(hist, self.cfg.regime)
        completed = frame.filter(frame["state"] != "warmup")
        if completed.height == 0:
            return True, "warmup", "none"
        row = completed.row(completed.height - 1, named=True)
        state, event = row["state"], row["event"]
        action = self.cfg.regime_action
        ok = {
            "trade_all": True,
            "bull_only": state == "bull",
            "retracement_only": event == "retracement",
            "any_event": event != "none",
        }[action]
        return ok, state, event

    def _risk_dollars(self, plan: DiagonalPlan, view: MarketView) -> float:
        mode = self.cfg.sizing.risk_definition
        legs = list(plan.leg_states)
        if mode == "scenario":
            return r_scenario(legs, view.spot)
        if mode == "width":
            return r_width(legs)
        if mode == "margin":
            return r_margin(legs)
        raise ValueError(mode)

    def _log_skip(self, entry_session: dt.date, reason: str) -> None:
        self.week_log.append({"entry_session": entry_session, "traded": False, "reason": reason})

    def _maybe_enter(self, view: MarketView, portfolio: Portfolio, broker: BrokerLike) -> None:
        is_entry = self._is_entry_session(view)
        eod_mode = self.cfg.entry.execution in ("eod_mid", "eod_immediate")
        if eod_mode:
            if not (is_entry and view.is_last_bar_of_session):
                return
        elif not in_entry_window(
            view.ts,
            view.session_date,
            is_entry,
            view.is_second_last_session_of_week,
            self.cfg.entry,
        ):
            return
        entry_session = view.session_date if is_entry else (view.next_session or view.session_date)
        if entry_session in self._entry_sessions_handled:
            if not eod_mode:
                self._maybe_relax(view, broker, entry_session)
            return
        # blocked while an existing cycle's front legs are still alive BEYOND
        # today — a cycle whose scheduled early exit fires today does NOT
        # block (its close and the new entry share the EOD bar):
        if any(
            cy.front_expiry > view.session_date
            and not cy.t1_done
            and not self._exit_due(cy, view.session_date)
            for cy in self.cycles
        ):
            return

        allowed, state, event = self._regime_allows(view)
        if not allowed:
            self._entry_sessions_handled.add(entry_session)
            self._log_skip(entry_session, f"regime {state}/{event}")
            return

        plan = build_diagonal(view, self.cfg.structure)
        if plan is None or (self.cfg.structure.require_credit and plan.mid_credit <= 0):
            self._entry_sessions_handled.add(entry_session)
            self._log_skip(entry_session, "no viable structure")
            return

        r_dollars = self._risk_dollars(plan, view)
        worst, best = scenario_extremes(list(plan.leg_states), view.spot)
        ref = reference_points(plan, self.cfg.entry, max(-worst, 0.0), max(best, 0.0))
        min_credit = self.cfg.structure.min_credit_frac * (r_dollars / 100.0)
        thresholds = [max(t, min_credit) for t in rung_credit_thresholds(self.cfg.entry, ref)]

        nav = self._nav_estimate(view, portfolio)
        qty = min(
            contracts_for_risk(self.cfg.sizing.risk_fraction, nav, r_dollars),
            self.cfg.sizing.max_contracts,
        )
        if qty < 1:
            self._entry_sessions_handled.add(entry_session)
            self._log_skip(entry_session, "size 0")
            return

        cycle = CycleState(
            entry_session=entry_session, plan=plan, r_dollars=r_dollars, qty_target=qty
        )
        gu = window_end(entry_session)
        if eod_mode:
            if self.cfg.structure.require_credit and plan.mid_credit < thresholds[0]:
                self._entry_sessions_handled.add(entry_session)
                self._log_skip(entry_session, "credit below threshold at close")
                return
            if self.cfg.entry.execution == "eod_immediate":
                # marketable close order: fills at mid + k_exit * half-spread —
                # the only fillable Track-B entry for debit structures
                cycle.order_ids.append(
                    broker.submit(legs=plan.legs, qty=qty, max_net_debit=None, immediate=True)
                )
            else:
                cycle.order_ids.append(
                    broker.submit(
                        legs=plan.legs, qty=qty, max_net_debit=-plan.mid_credit, good_until=gu
                    )
                )
        else:
            for rung_qty, threshold in zip(
                split_quantity(qty, len(thresholds)), thresholds, strict=True
            ):
                if rung_qty < 1:
                    continue
                cycle.order_ids.append(
                    broker.submit(
                        legs=plan.legs, qty=rung_qty, max_net_debit=-threshold, good_until=gu
                    )
                )
        self.cycles.append(cycle)
        self._entry_sessions_handled.add(entry_session)
        self.week_log.append(
            {
                "entry_session": entry_session,
                "traded": True,
                "reason": f"regime {state}/{event}",
                "qty_target": qty,
                "r_dollars": r_dollars,
                "thresholds": thresholds,
            }
        )

    def _maybe_relax(self, view: MarketView, broker: BrokerLike, entry_session: dt.date) -> None:
        cfg = self.cfg.entry
        cy = next((c for c in self.cycles if c.entry_session == entry_session), None)
        if (
            cfg.no_fill_policy != "relax"
            or cy is None
            or cy.relaxed
            or cy.entry_fills > 0
            or view.session_date != entry_session
            or view.ts.time() < cfg.relax_at
        ):
            return
        new_ids: list[int] = []
        for oid in cy.order_ids:
            order = broker.orders.get(oid)
            if order is None or order.remaining <= 0 or order.max_net_debit is None:
                continue
            broker.cancel(oid)
            new_ids.append(
                broker.submit(
                    legs=order.legs,
                    qty=order.remaining,
                    max_net_debit=order.max_net_debit * (1.0 - cfg.relax_frac),
                    good_until=order.good_until,
                )
            )
        cy.order_ids.extend(new_ids)
        cy.relaxed = True

    # ----------------------------------------------------------- holding --
    def _sync_entry_fills(self, portfolio: Portfolio) -> None:
        for cy in self.cycles:
            oid_set = set(cy.order_ids)
            fills = [f for f in portfolio.fills if f.order_id in oid_set]
            cy.entry_fills = sum(f.qty for f in fills)
            cy.entry_credit_points = -sum(f.price_debit * f.qty for f in fills)

    def _position_pnl_dollars(self, cy: CycleState, view: MarketView) -> float | None:
        if cy.entry_fills == 0:
            return None
        value = 0.0
        for key, ratio in cy.plan.legs:
            q = view.quote(key)
            # marks (unlike fills) accept one-sided quotes: a zero-bid deep-OTM
            # wing is worth ~ask/2, and refusing to value it would blind the
            # pnl_floor trigger in exactly the states it exists for
            if q is None or not q.sane:
                return None
            value += ratio * (q.bid + q.ask) / 2.0
        return (cy.entry_credit_points + value * cy.entry_fills) * 100.0

    def _maybe_defend(self, view: MarketView, portfolio: Portfolio, broker: BrokerLike) -> None:
        cfg = self.cfg.defense
        if cfg.trigger == "none":
            return
        for cy in self.cycles:
            if cy.entry_fills == 0 or view.session_date > cy.front_expiry:
                continue
            side_now = dfs.tested_side(
                cfg,
                view,
                cy.plan.short_put,
                cy.plan.short_call,
                self._position_pnl_dollars(cy, view),
                cy.r_dollars,
                at_session_close=view.is_last_bar_of_session,
            )
            if side_now is not None and cy.tested_memory is None:
                cy.tested_memory = side_now

            act_side: str | None = None
            if cfg.timing == "immediate" and side_now is not None:
                act_side = side_now
            elif cfg.timing == "eod" and view.is_last_bar_of_session and side_now is not None:
                act_side = side_now
            elif cfg.timing in ("t_minus_1", "hybrid"):
                at_t1_close = view.is_last_bar_of_session and view.next_session == cy.front_expiry
                if at_t1_close:
                    act_side = side_now if cfg.timing == "t_minus_1" else cy.tested_memory
            if act_side is None or act_side in cy.defended_sides:
                self._maybe_harvest_untested(cy, view, portfolio, broker)
                continue

            cy.defended_sides.add(act_side)
            self.defense_log.append(
                {
                    "entry_session": cy.entry_session,
                    "ts": view.ts,
                    "side": act_side,
                    "trigger": cfg.trigger,
                    "timing": cfg.timing,
                    "action": cfg.action,
                    "spot": view.spot,
                }
            )
            if cfg.action == "delta_hedge":
                positions = dict(portfolio.option_positions())
                delta = dfs.position_delta_dollars_per_point(view, positions)
                units = -delta - cy.hedge_units
                portfolio.trade_index(units, view.spot)
                cy.hedge_units += units
            else:
                legs = dfs.action_legs(cfg, act_side, view, cy.plan.legs)
                if legs is not None:
                    broker.submit(legs=legs, qty=cy.entry_fills, max_net_debit=None, immediate=True)
            self._maybe_harvest_untested(cy, view, portfolio, broker)

    def _maybe_harvest_untested(
        self, cy: CycleState, view: MarketView, portfolio: Portfolio, broker: BrokerLike
    ) -> None:
        cfg = self.cfg.defense
        if (
            cfg.untested != "harvest_80"
            or cy.harvested
            or cy.tested_memory is None
            or cy.entry_fills == 0
        ):
            return
        untested = cy.plan.short_call if cy.tested_memory == "put" else cy.plan.short_put
        if portfolio.positions.get(untested, 0) >= 0:
            return  # already bought back / rolled
        q = view.quote(untested)
        if q is None or not q.sane:
            return
        mid = (q.bid + q.ask) / 2.0
        entry_state = next(s for s in cy.plan.leg_states if s.key == untested)
        if mid <= 0.20 * entry_state.mid:
            broker.submit(
                legs=((untested, +1),), qty=cy.entry_fills, max_net_debit=None, immediate=True
            )
            cy.harvested = True

    def _exit_due(self, cy: CycleState, session: dt.date) -> bool:
        return (
            self.cfg.exit_dte is not None
            and session > cy.entry_session
            and (cy.front_expiry - session).days <= self.cfg.exit_dte
        )

    def _maybe_t1(self, view: MarketView, portfolio: Portfolio, broker: BrokerLike) -> None:
        for cy in self.cycles:
            t1_hit = (
                self.cfg.manage_t1 == "close_all"
                and view.next_session == cy.front_expiry
            )
            if (
                cy.t1_done
                or cy.entry_fills == 0
                or not view.is_last_bar_of_session
                or not (t1_hit or self._exit_due(cy, view.session_date))
            ):
                continue
            legs = tuple(
                (key, -ratio)
                for key, ratio in cy.plan.legs
                if portfolio.positions.get(key, 0) * ratio > 0
            )
            if legs:
                broker.submit(legs=legs, qty=cy.entry_fills, max_net_debit=None, immediate=True)
            cy.t1_done = True

    def _nav_estimate(self, view: MarketView, portfolio: Portfolio) -> float:
        from options_strategy.engine.marks import mark_positions

        if not portfolio.positions:
            return portfolio.cash
        return portfolio.nav(mark_positions(portfolio, view))

    # -------------------------------------------------------------- main --
    def on_bar(self, view: MarketView, portfolio: Portfolio, broker: BrokerLike) -> None:
        # Fills from the PREVIOUS bar's broker evaluation must be synced before
        # pruning, or a freshly-filled cycle would look unfilled and be dropped.
        self._sync_entry_fills(portfolio)
        self.cycles = [
            cy
            for cy in self.cycles
            if view.session_date <= cy.front_expiry
            and not (cy.entry_fills == 0 and view.ts > window_end(cy.entry_session))
        ]
        self._maybe_enter(view, portfolio, broker)
        self._sync_entry_fills(portfolio)
        self._maybe_defend(view, portfolio, broker)
        self._maybe_t1(view, portfolio, broker)
