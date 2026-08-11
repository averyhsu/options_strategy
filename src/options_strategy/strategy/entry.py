"""EV-gated resting entries (PLAN §8.2): credit thresholds against a
configurable reference, laddered child orders, entry windows and the
no-fill policy.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from options_strategy.data.schemas import ET
from options_strategy.strategy.diagonal import DiagonalPlan

_ET = ZoneInfo(ET)


class EntryConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    credit_threshold_frac: float = 0.30
    threshold_reference: str = "width"  # width | scenario_r | max_gain
    # resting: EV-gated GTC ladder inside the order window (the real mechanism)
    # eod_mid: fill the full size at the entry-session CLOSE MID when the base
    #          threshold is met — the EOD-expressible mode Track A compiles to
    #          (PLAN §7.5; used by the A==B consistency test).
    # eod_immediate: marketable order at the entry-session close, paying
    #          mid + k_exit * half-spread (evaluate_immediate pricing). The
    #          only Track-B-fillable entry for DEBIT structures under
    #          CONSERVATIVE/MID (a debit can't rest at a credit limit and a
    #          limit AT mid only fills under OPTIMISTIC) — used by the
    #          percentile-family companion grid (ASSUMPTIONS.md 2026-08-11).
    execution: str = "resting"
    order_window: str = "fri_open_close"  # fri_open_close | thu14_fri_close
    ladder_rungs: int = 1  # 1..3, rising thresholds
    ladder_step_frac: float = 0.05  # extra threshold per rung (x reference)
    no_fill_policy: str = "skip"  # skip | relax
    relax_frac: float = 0.10  # threshold cut applied at 15:30 on entry day
    relax_at: dt.time = dt.time(15, 30)


def reference_points(
    plan: DiagonalPlan, cfg: EntryConfig, r_scenario_dollars: float, best_gain_dollars: float
) -> float:
    if cfg.threshold_reference == "width":
        return plan.reference_width
    if cfg.threshold_reference == "scenario_r":
        return r_scenario_dollars / 100.0
    if cfg.threshold_reference == "max_gain":
        return best_gain_dollars / 100.0
    raise ValueError(cfg.threshold_reference)


def rung_credit_thresholds(cfg: EntryConfig, reference: float) -> list[float]:
    """Ascending credit thresholds (points), one per ladder rung."""
    base = cfg.credit_threshold_frac * reference
    return [base + i * cfg.ladder_step_frac * reference for i in range(cfg.ladder_rungs)]


def split_quantity(total: int, rungs: int) -> list[int]:
    """Near-even split, remainder to the earliest (cheapest-threshold) rungs."""
    if total <= 0:
        return [0] * rungs
    base, extra = divmod(total, rungs)
    return [base + (1 if i < extra else 0) for i in range(rungs)]


def in_entry_window(
    ts: dt.datetime,
    session_date: dt.date,
    is_entry_session: bool,
    prev_is_entry_eve: bool,
    cfg: EntryConfig,
) -> bool:
    """Is this bar inside the order window?

    fri_open_close: any bar of the entry session.
    thu14_fri_close: bars >= 14:00 on the session BEFORE the entry session,
    plus all of the entry session.
    """
    if cfg.order_window == "fri_open_close":
        return is_entry_session
    if cfg.order_window == "thu14_fri_close":
        if is_entry_session:
            return True
        return prev_is_entry_eve and ts.astimezone(_ET).time() >= dt.time(14, 0)
    raise ValueError(cfg.order_window)


def window_end(entry_session: dt.date) -> dt.datetime:
    return dt.datetime.combine(entry_session, dt.time(16, 0), tzinfo=_ET)
