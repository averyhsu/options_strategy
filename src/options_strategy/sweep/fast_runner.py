"""Lean Track-A evaluator for the coarse sweep: one config against the
precomputed WorldCache. Decision-for-decision it replicates
`engine.track_a.run_track_a` (eod_mid entries, EOD defense proxy, official
settlements, same fees and sizing) — the equivalence test in
tests/integration/test_sweep_equivalence.py holds the two within 1e-6 NAV.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from options_strategy.engine import CONTRACT_MULTIPLIER
from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.margin import LegState, ScenarioGrid, contracts_for_risk
from options_strategy.pricing import black76
from options_strategy.strategy.bands import band_edges
from options_strategy.strategy.weekly import WeeklyConfig
from options_strategy.sweep.precompute import SessionData, Side, WorldCache

Leg = tuple[dt.date, str, float, int]  # (expiry, cp, strike, ratio)


@dataclass
class SweepResult:
    nav_daily: np.ndarray
    sessions: list[dt.date]
    cycles: list[dict]  # entry_session, qty, r_dollars, credit, pnl_dollars
    n_fills: int
    fees_paid: float


def _side(sd: SessionData, expiry: dt.date, cp: str) -> Side | None:
    return sd.sides.get((expiry, cp))


def _mid_at(sd: SessionData, leg: Leg) -> float | None:
    side = _side(sd, leg[0], leg[1])
    if side is None:
        return None
    i = np.searchsorted(side.strikes, leg[2])
    if i < len(side.strikes) and side.strikes[i] == leg[2]:
        return float(side.mid[i])
    return None


def _model_mark(sd: SessionData, leg: Leg) -> float | None:
    """Interp-IV fallback, formula-identical to engine.marks._model_mark."""
    fit = sd.forwards.get(leg[0])
    side = _side(sd, leg[0], leg[1])
    if fit is None or side is None:
        return None
    f_hat, df_hat, tau = fit
    good = np.isfinite(side.iv)
    if good.sum() < 2:
        return None
    iv_k = float(np.interp(leg[2], side.strikes[good], side.iv[good]))
    return float(black76.price(f_hat, leg[2], tau, iv_k, df_hat, cp=1 if leg[1] == "C" else -1))


def _mark(sd: SessionData, leg: Leg) -> float:
    if leg[0] == sd.session:  # expiring today: intrinsic at the close print
        w = 1.0 if leg[1] == "C" else -1.0
        return max(w * (sd.close - leg[2]), 0.0)
    m = _mid_at(sd, leg)
    if m is not None:
        return m
    model = _model_mark(sd, leg)
    if model is not None:
        return model
    # unmarkable wing: intrinsic-at-spot floor (matches engine.marks)
    w = 1.0 if leg[1] == "C" else -1.0
    return max(w * (sd.close - leg[2]), 0.0)


def _pick_expiries(sd: SessionData, cfg: WeeklyConfig) -> tuple[dt.date, dt.date, dt.date] | None:
    s = cfg.structure
    today = sd.session
    front = next(
        (e for e in sd.expiries if s.front_min_days <= (e - today).days <= s.front_max_days),
        None,
    )
    if front is None:
        return None
    back_put = next(
        (e for e in sd.expiries if (e - front).days >= s.long_put_expiry_offset_days), None
    )
    back_call = next(
        (e for e in sd.expiries if (e - front).days >= s.long_call_expiry_offset_days), None
    )
    if back_put is None or back_call is None:
        return None
    return front, back_put, back_call


def _strike_by_delta(sd: SessionData, expiry: dt.date, cp: str, target: float) -> float | None:
    fit = sd.forwards.get(expiry)
    side = _side(sd, expiry, cp)
    if fit is None or side is None:
        return None
    f_hat = fit[0]
    otm = side.strikes < f_hat if cp == "P" else side.strikes > f_hat
    good = otm & np.isfinite(side.delta_abs)
    if good.sum() < 2:
        return None
    k = side.strikes[good]
    d = side.delta_abs[good]
    return float(k[int(np.argmin(np.abs(d - target)))])


def _nearest_listed(sd: SessionData, expiry: dt.date, cp: str, target: float) -> float | None:
    side = _side(sd, expiry, cp)
    if side is None or len(side.strikes) == 0:
        return None
    return float(side.strikes[int(np.argmin(np.abs(side.strikes - target)))])


def _leg_state(sd: SessionData, leg: Leg) -> LegState | None:
    side = _side(sd, leg[0], leg[1])
    fit = sd.forwards.get(leg[0])
    if side is None or fit is None:
        return None
    i = np.searchsorted(side.strikes, leg[2])
    if i >= len(side.strikes) or side.strikes[i] != leg[2]:
        return None
    iv = side.iv[i]
    if not np.isfinite(iv):
        return None
    return LegState(
        key=OptionKey("SPXW", leg[0], leg[2], leg[1]),
        ratio=leg[3],
        mid=float(side.mid[i]),
        iv=float(iv),
        tau=fit[2],
        forward=fit[0],
        df=fit[1],
    )


def scenario_extremes_fast(
    legs: list[LegState], spot: float, grid: ScenarioGrid | None = None
) -> tuple[float, float]:
    """Vectorized twin of margin.scenario_extremes (allclose-tested)."""
    grid = grid or ScenarioGrid()
    front_tau = min(x.tau for x in legs)
    entry_debit = sum(x.ratio * x.mid for x in legs)
    s_mults = np.arange(-grid.s_range, grid.s_range + grid.s_step / 2, grid.s_step)
    s_prime = spot * (1.0 + s_mults)  # (S,)
    vshifts = np.asarray(grid.vol_shifts)  # (V,)
    total = np.zeros((len(s_mults), len(vshifts)))
    for x in legs:
        w = 1 if x.key.cp == "C" else -1
        tau_left = x.tau - front_tau
        if tau_left <= 1e-9:
            payoff = np.maximum(w * (s_prime - x.key.strike), 0.0)[:, None]
            total = total + x.ratio * payoff
        else:
            carry = math.log(x.forward / spot) / x.tau
            f_prime = s_prime * math.exp(carry * tau_left)
            r_rate = -math.log(x.df) / x.tau if x.df > 0 else 0.0
            df_prime = math.exp(-r_rate * tau_left)
            iv_prime = np.maximum(x.iv * (1.0 + vshifts), 1e-4)
            fgrid = np.repeat(f_prime[:, None], len(vshifts), axis=1)
            vgrid = np.repeat(iv_prime[None, :], len(s_mults), axis=0)
            px = black76.price(fgrid, x.key.strike, tau_left, vgrid, df_prime, cp=w)
            total = total + x.ratio * px
    pnl = (total - entry_debit) * CONTRACT_MULTIPLIER
    return float(min(pnl.min(), 0.0)), float(max(pnl.max(), 0.0))


def _risk_dollars(cfg: WeeklyConfig, legs: list[LegState], spot: float) -> float:
    mode = cfg.sizing.risk_definition
    if mode == "scenario":
        worst, _ = scenario_extremes_fast(legs, spot)
        return max(-worst, 0.0)
    entry_debit = sum(x.ratio * x.mid for x in legs)
    width = 0.0
    for cp in ("C", "P"):
        shorts = [x for x in legs if x.key.cp == cp and x.ratio < 0]
        longs = [x for x in legs if x.key.cp == cp and x.ratio > 0]
        for s_leg in shorts:
            if not longs:
                return 0.0
            nearest = min(longs, key=lambda y: abs(y.key.strike - s_leg.key.strike))
            width = max(width, abs(nearest.key.strike - s_leg.key.strike))
    if mode == "width":
        return max((width + entry_debit) * CONTRACT_MULTIPLIER, 0.0)
    if mode == "margin":
        return width * CONTRACT_MULTIPLIER
    raise ValueError(mode)


def run_config(
    cache: WorldCache,
    cfg: WeeklyConfig,
    initial_cash: float,
    fees_per_leg: float,
    participation_cap: float,
) -> SweepResult:
    cash = initial_cash
    fees_paid = 0.0
    n_fills = 0
    positions: dict[Leg, int] = {}
    cycles: list[dict] = []
    open_cycles: list[dict] = []
    nav_daily = np.empty(len(cache.sessions))
    regime_table = cache.regime_allow[(cfg.regime.ema_len, cfg.regime.hysteresis_atr)]
    band_table = (
        cache.band_returns.get(cfg.structure.band_ema_len, {})
        if cfg.structure.strike_family == "percentile"
        else {}
    )

    def close_side(sd: SessionData, cy: dict, side_name: str) -> None:
        nonlocal cash, fees_paid, n_fills
        cp = "P" if side_name == "put" else "C"
        short = next(leg for leg in cy["legs"] if leg[1] == cp and leg[3] < 0)
        long_ = next(leg for leg in cy["legs"] if leg[1] == cp and leg[3] > 0)
        m_short, m_long = _mid_at(sd, short), _mid_at(sd, long_)
        if m_short is None or m_long is None:
            return
        qty = cy["qty"]
        debit = m_short - m_long
        cash -= debit * qty * CONTRACT_MULTIPLIER
        fees = fees_per_leg * qty * 2
        cash -= fees
        fees_paid += fees
        n_fills += 1
        positions[short] = positions.get(short, 0) + qty
        positions[long_] = positions.get(long_, 0) - qty
        for leg in (short, long_):
            if positions.get(leg) == 0:
                positions.pop(leg)
        cy["defended"].add(side_name)

    for i, session in enumerate(cache.sessions):
        sd = cache.by_session.get(session)

        # order per session mirrors run_track_a: prune -> defense proxy ->
        # entry -> PM settlements -> mark.
        open_cycles = [c for c in open_cycles if session <= c["front"]]

        if (
            cfg.defense.trigger == "close_beyond"
            and cfg.defense.action == "close_tested_side"
            and sd is not None
        ):
            for cy in open_cycles:
                spot = sd.close
                if spot <= cy["short_put"] and "put" not in cy["defended"]:
                    close_side(sd, cy, "put")
                elif spot >= cy["short_call"] and "call" not in cy["defended"]:
                    close_side(sd, cy, "call")

        can_enter = (
            cache.entry_flags[i]
            and sd is not None
            and not any(c["front"] > session for c in open_cycles)
        )
        if can_enter:
            state, event = regime_table.get(session, ("warmup", "none"))
            allowed = (
                state == "warmup"
                or {
                    "trade_all": True,
                    "bull_only": state == "bull",
                    "retracement_only": event == "retracement",
                    "any_event": event != "none",
                }[cfg.regime_action]
            )
            if allowed:
                plan = _build_plan(sd, cfg, band_table.get(session))
                if plan is not None:
                    legs, leg_states, mid_credit, width = plan
                    if mid_credit > 0 or not cfg.structure.require_credit:
                        r_dollars = _risk_dollars(cfg, leg_states, sd.close)
                        worst, best = scenario_extremes_fast(leg_states, sd.close)
                        ref = {
                            "width": width,
                            "scenario_r": max(-worst, 0.0) / 100.0,
                            "max_gain": max(best, 0.0) / 100.0,
                        }[cfg.entry.threshold_reference]
                        threshold = max(
                            cfg.entry.credit_threshold_frac * ref,
                            cfg.structure.min_credit_frac * (r_dollars / 100.0),
                        )
                        if (not cfg.structure.require_credit) or mid_credit >= threshold:
                            nav_now = cash + _mtm(positions, sd)
                            qty = min(
                                contracts_for_risk(cfg.sizing.risk_fraction, nav_now, r_dollars),
                                cfg.sizing.max_contracts,
                            )
                            cap = _size_cap(sd, legs)
                            qty = min(qty, int(cap * participation_cap))
                            if qty >= 1:
                                debit = -mid_credit
                                cash -= debit * qty * CONTRACT_MULTIPLIER
                                fees = fees_per_leg * qty * 4
                                cash -= fees
                                fees_paid += fees
                                n_fills += 1
                                for leg in legs:
                                    positions[leg] = positions.get(leg, 0) + leg[3] * qty
                                cy = {
                                    "entry_session": session,
                                    "entry_i": i,
                                    "front": legs[0][0],
                                    "short_put": legs[0][2],
                                    "short_call": legs[1][2],
                                    "legs": legs,
                                    "qty": qty,
                                    "r_dollars": r_dollars,
                                    "credit": mid_credit,
                                    "defended": set(),
                                    "nav_before": nav_daily[i - 1] if i > 0 else initial_cash,
                                }
                                open_cycles.append(cy)
                                cycles.append(cy)

        # settlements (SPXW PM)
        for leg in [x for x in positions if x[0] == session]:
            qty = positions.pop(leg)
            settle = cache.settlements[session]
            w = 1.0 if leg[1] == "C" else -1.0
            cash += max(w * (settle - leg[2]), 0.0) * qty * CONTRACT_MULTIPLIER

        nav_daily[i] = cash + (_mtm(positions, sd) if sd is not None else 0.0)

    for cy in cycles:
        end_i = next(
            (j for j, s in enumerate(cache.sessions) if s >= cy["front"]),
            len(cache.sessions) - 1,
        )
        cy["pnl_dollars"] = float(nav_daily[end_i] - cy["nav_before"])
        cy.pop("legs", None)
        cy.pop("defended", None)

    return SweepResult(
        nav_daily=nav_daily,
        sessions=cache.sessions,
        cycles=cycles,
        n_fills=n_fills,
        fees_paid=fees_paid,
    )


def _build_plan(sd: SessionData, cfg: WeeklyConfig, band_arr: np.ndarray | None = None):
    s = cfg.structure
    exp = _pick_expiries(sd, cfg)
    if exp is None:
        return None
    front, back_put, back_call = exp
    if s.strike_family == "percentile":
        edges = band_edges(
            band_arr if band_arr is not None else np.empty(0),
            s.coverage_q_put,
            s.coverage_q_call,
            s.min_band_obs,
        )
        if edges is None:
            return None
        sp = _nearest_listed(sd, front, "P", sd.close * (1.0 + edges[0]))
        sc = _nearest_listed(sd, front, "C", sd.close * (1.0 + edges[1]))
    else:
        sp = _strike_by_delta(sd, front, "P", s.short_put_delta)
        sc = _strike_by_delta(sd, front, "C", s.short_call_delta)
    if sp is None or sc is None or sp >= sc:
        return None
    lp = _nearest_listed(sd, back_put, "P", sp - s.long_strike_offset)
    lc = _nearest_listed(sd, back_call, "C", sc + s.long_strike_offset)
    if lp is None or lc is None:
        return None
    legs: tuple[Leg, ...] = (
        (front, "P", sp, -1),
        (front, "C", sc, -1),
        (back_put, "P", lp, +1),
        (back_call, "C", lc, +1),
    )
    states = []
    for leg in legs:
        st = _leg_state(sd, leg)
        if st is None:
            return None
        states.append(st)
    mid_credit = -sum(x.ratio * x.mid for x in states)
    width = max(abs(sp - lp), abs(sc - lc))
    return legs, states, mid_credit, width


def _mtm(positions: dict[Leg, int], sd: SessionData | None) -> float:
    if not positions:
        return 0.0
    if sd is None:
        raise RuntimeError("open positions with no session data")
    total = 0.0
    for leg, qty in positions.items():
        total += qty * _mark(sd, leg) * CONTRACT_MULTIPLIER
    return total


def _size_cap(sd: SessionData, legs: tuple[Leg, ...]) -> int:
    cap = 10**9
    for expiry, cp, strike, ratio in legs:
        side = _side(sd, expiry, cp)
        if side is None:
            return 0
        i = np.searchsorted(side.strikes, strike)
        if i >= len(side.strikes) or side.strikes[i] != strike:
            return 0
        size = side.ask_size[i] if ratio > 0 else side.bid_size[i]
        cap = min(cap, int(size))
    return cap
