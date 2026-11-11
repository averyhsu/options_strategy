"""Track A: the weekly config compiled to daily-close logic (PLAN §7.5).

Entries fill the full size at the entry-session CLOSE MID when the regime
allows and the base credit threshold is met on the EOD chain — identical
semantics to the weekly strategy's `execution: eod_mid` mode, which is what
the Track A == Track B consistency test exploits (PLAN §3). No intraday
defense; `close_beyond` + `close_tested_side` is honored as an EOD proxy for
pruning (PLAN §9.1); anything else in the defense config is out of Track A's
expressible set and ignored. Settlement at official values; same fees; same
portfolio accounting (so conservation checks run here too).
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import BacktestResult, _settle
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.margin import contracts_for_risk, scenario_extremes
from options_strategy.engine.marketview import MarketView
from options_strategy.engine.marks import mark_positions
from options_strategy.engine.portfolio import Portfolio
from options_strategy.pricing.settlement import SettlementTable
from options_strategy.strategy.defense import tested_side
from options_strategy.strategy.diagonal import build_diagonal
from options_strategy.strategy.entry import reference_points, rung_credit_thresholds
from options_strategy.strategy.weekly import CycleState, DoubleDiagonalWeekly, WeeklyConfig


def run_track_a(
    adapter: SyntheticWorldAdapter,
    cfg: WeeklyConfig,
    engine_cfg: EngineConfig | None = None,
    initial_cash: float | None = None,
) -> BacktestResult:
    engine_cfg = engine_cfg or EngineConfig()
    portfolio = Portfolio(initial_cash if initial_cash is not None else engine_cfg.account_size)
    settle_table = SettlementTable(adapter.settlements())
    forwards_all = adapter.forwards_extracted()
    flags_all = adapter.quality_flags()
    key_cols = ["ts", "root", "expiry_date", "strike", "cp"]

    underlying = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    daily_all = underlying.group_by("session", maintain_order=True).agg(
        open=pl.col("open").first(),
        high=pl.col("high").max(),
        low=pl.col("low").min(),
        close=pl.col("close").last(),
    )
    sessions = adapter.sessions()
    expiries = adapter.expiries()
    session_list = sessions["session"].to_list()
    n = len(session_list)
    iso_weeks = [(d.isocalendar().year, d.isocalendar().week) for d in session_list]
    last_of_week = [i == n - 1 or iso_weeks[i + 1] != iso_weeks[i] for i in range(n)]

    gate = DoubleDiagonalWeekly(cfg)  # reused only for _regime_allows / helpers
    cycles: list[CycleState] = []
    fake_order_id = 10_000
    daily_rows: list[dict] = []
    result = BacktestResult(daily=pl.DataFrame(), portfolio=portfolio)

    for i, session in enumerate(session_list):
        _settle(portfolio, settle_table, expiries, session, kind="AM")

        quotes_day = adapter.option_quotes(session)
        quotes_day = quotes_day.join(
            flags_all.select([*key_cols, "flags"]), on=key_cols, how="left"
        ).with_columns(pl.col("flags").fill_null(0))
        eod_ts_raw = quotes_day["ts"].max()
        assert isinstance(eod_ts_raw, dt.datetime)
        eod_ts = eod_ts_raw
        chain = quotes_day.filter(pl.col("ts") == eod_ts)
        day = daily_all.row(i, named=True)
        view = MarketView(
            ts=eod_ts,
            spot=float(day["close"]),
            chain=chain,
            forwards=forwards_all.filter(pl.col("ts") == eod_ts),
            session_date=session,
            is_last_bar_of_session=True,
            daily_history=daily_all[:i],
            today_open=float(day["open"]),
            today_high=float(day["high"]),
            today_low=float(day["low"]),
            is_last_session_of_week=last_of_week[i],
            next_session=session_list[i + 1] if i + 1 < n else None,
        )

        cycles = [cy for cy in cycles if session <= cy.front_expiry]

        # EOD defense proxy (PLAN §9.1: defense collapsed to {none, close-side-EOD})
        if cfg.defense.trigger == "close_beyond" and cfg.defense.action == "close_tested_side":
            for cy in cycles:
                if cy.entry_fills == 0 or session > cy.front_expiry:
                    continue
                side = tested_side(
                    cfg.defense,
                    view,
                    cy.plan.short_put,
                    cy.plan.short_call,
                    None,
                    cy.r_dollars,
                    at_session_close=True,
                )
                if side is None or side in cy.defended_sides:
                    continue
                short, long_ = (
                    (cy.plan.legs[0][0], cy.plan.legs[2][0])
                    if side == "put"
                    else (cy.plan.legs[1][0], cy.plan.legs[3][0])
                )
                close_legs: tuple[tuple[OptionKey, int], ...] = ((short, +1), (long_, -1))
                mid_debit = 0.0
                ok = True
                for key, ratio in close_legs:
                    q = view.quote(key)
                    if q is None or not q.sane or q.bid <= 0:
                        ok = False
                        break
                    mid_debit += ratio * ((q.bid + q.ask) / 2.0)
                if ok:
                    # defended only on an EXECUTED close; bad quotes retry the
                    # next session (never fill against unusable data).
                    cy.defended_sides.add(side)
                    fake_order_id += 1
                    portfolio.apply_combo_fill(
                        ts=eod_ts,
                        order_id=fake_order_id,
                        legs=close_legs,
                        qty=cy.entry_fills,
                        price_debit=mid_debit,
                        fees=engine_cfg.fees.fill_fee(cy.entry_fills, n_legs=len(close_legs)),
                    )

        # scheduled early exit (exit_dte): close every still-open leg of a
        # due cycle at EOD mid — mirrors weekly._maybe_t1 / fast_runner
        if cfg.exit_dte is not None:
            for cy in cycles:
                if (
                    cy.t1_done
                    or cy.entry_fills == 0
                    or session <= cy.entry_session
                    or (cy.front_expiry - session).days > cfg.exit_dte
                ):
                    continue
                close_legs = tuple(
                    (key, -ratio)
                    for key, ratio in cy.plan.legs
                    if portfolio.positions.get(key, 0) * ratio > 0
                )
                mid_debit = 0.0
                ok = bool(close_legs)
                for key, ratio in close_legs:
                    q = view.quote(key)
                    if q is None or not q.sane or q.bid <= 0:
                        ok = False
                        break
                    mid_debit += ratio * ((q.bid + q.ask) / 2.0)
                if ok:
                    fake_order_id += 1
                    portfolio.apply_combo_fill(
                        ts=eod_ts,
                        order_id=fake_order_id,
                        legs=close_legs,
                        qty=cy.entry_fills,
                        price_debit=mid_debit,
                        fees=engine_cfg.fees.fill_fee(cy.entry_fills, n_legs=len(close_legs)),
                    )
                    cy.t1_done = True

        # entry at the close
        is_entry = session.weekday() == 4 or last_of_week[i]
        live_beyond_today = any(
            cy.front_expiry > session
            and not cy.t1_done
            and not (
                cfg.exit_dte is not None
                and session > cy.entry_session
                and (cy.front_expiry - session).days <= cfg.exit_dte
            )
            for cy in cycles
        )
        if is_entry and not live_beyond_today:
            allowed, _state, _event = gate._regime_allows(view)
            if allowed:
                plan = build_diagonal(view, cfg.structure)
                if plan is not None and (plan.mid_credit > 0 or not cfg.structure.require_credit):
                    r_dollars = gate._risk_dollars(plan, view)
                    worst, best = scenario_extremes(list(plan.leg_states), view.spot)
                    ref = reference_points(plan, cfg.entry, max(-worst, 0.0), max(best, 0.0))
                    min_credit = cfg.structure.min_credit_frac * (r_dollars / 100.0)
                    thresholds = [
                        max(t, min_credit) for t in rung_credit_thresholds(cfg.entry, ref)
                    ]
                    if (not cfg.structure.require_credit) or plan.mid_credit >= thresholds[0]:
                        nav = (
                            portfolio.cash
                            if not portfolio.positions
                            else portfolio.nav(mark_positions(portfolio, view))
                        )
                        qty = min(
                            contracts_for_risk(cfg.sizing.risk_fraction, nav, r_dollars),
                            cfg.sizing.max_contracts,
                        )
                        # same displayed-size participation cap as Track B
                        cap = 10**9
                        for key, ratio in plan.legs:
                            q = view.quote(key)
                            if q is None:
                                cap = 0
                                break
                            size = q.ask_size if ratio > 0 else q.bid_size
                            cap = min(cap, size // abs(ratio))
                        qty = min(qty, int(cap * engine_cfg.participation_cap))
                        if qty >= 1:
                            fake_order_id += 1
                            portfolio.apply_combo_fill(
                                ts=eod_ts,
                                order_id=fake_order_id,
                                legs=plan.legs,
                                qty=qty,
                                price_debit=-plan.mid_credit,
                                fees=engine_cfg.fees.fill_fee(qty, n_legs=len(plan.legs)),
                            )
                            cy = CycleState(
                                entry_session=session,
                                plan=plan,
                                r_dollars=r_dollars,
                                qty_target=qty,
                            )
                            cy.entry_fills = qty
                            cy.entry_credit_points = plan.mid_credit * qty
                            cycles.append(cy)

        _settle(portfolio, settle_table, expiries, session, kind="PM")

        marks = mark_positions(portfolio, view)
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

    result.daily = pl.DataFrame(daily_rows)
    return result
