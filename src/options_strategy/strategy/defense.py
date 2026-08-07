"""Defense policy DSL (PLAN §8.4) — the claimed edge, modeled as a small
enum-grid policy space that ABC can search.

trigger x timing x action x untested-side rule, all config. Actions build
IMMEDIATE combo orders from the live position (executed at mid + k_exit *
half-spread by the engine, gated on sane quotes). Concrete action semantics:

- close_tested_side: buy back the tested short AND sell the same-side long.
- buy_back_short: buy back the tested short only (go long-wing).
- close_all: unwind all four legs.
- roll_out: buy back tested short, sell same strike in the NEXT weekly expiry.
- roll_out_away: buy back tested short, sell next weekly at roll_target_delta.
- convert_vertical: buy back tested short, sell a new short in the SAME expiry
  as that side's long wing at roll_target_delta (leaves a vertical).
- delta_hedge: trade synthetic index units to flatten the position delta
  (handled by the weekly strategy, not an option combo).
- untested harvest_80: buy back the untested short once it has decayed to
  <= 20% of its entry value.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from pydantic import BaseModel, ConfigDict

from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.marketview import MarketView
from options_strategy.pricing.greeks import greeks
from options_strategy.pricing.iv import implied_vol

TRIGGERS = ("none", "touch", "close_beyond", "short_delta", "pnl_floor")
TIMINGS = ("immediate", "eod", "t_minus_1", "hybrid")
ACTIONS = (
    "nothing",
    "close_tested_side",
    "buy_back_short",
    "close_all",
    "roll_out",
    "roll_out_away",
    "convert_vertical",
    "delta_hedge",
)
UNTESTED = ("hold", "harvest_80")


class DefenseConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger: str = "none"
    trigger_delta: float = 0.50  # for trigger == short_delta
    trigger_pnl_frac: float = 0.50  # loss >= frac * R (trigger == pnl_floor)
    timing: str = "t_minus_1"
    action: str = "nothing"
    roll_target_delta: float = 0.20
    untested: str = "hold"

    def model_post_init(self, __context) -> None:
        for value, allowed in (
            (self.trigger, TRIGGERS),
            (self.timing, TIMINGS),
            (self.action, ACTIONS),
            (self.untested, UNTESTED),
        ):
            if value not in allowed:
                raise ValueError(f"{value!r} not in {allowed}")


def leg_abs_delta(view: MarketView, key: OptionKey) -> float | None:
    """Undiscounted |delta| of one option from the live chain."""
    q = view.quote(key)
    fit = view.forward(key.root, key.expiry)
    if q is None or not q.sane or q.bid <= 0 or fit is None:
        return None
    f_hat, df_hat, tau = fit
    mid = (q.bid + q.ask) / 2.0
    iv = float(implied_vol(mid, f_hat, key.strike, tau, df_hat, cp=1 if key.cp == "C" else -1))
    if not np.isfinite(iv):
        return None
    g = greeks(f_hat, key.strike, tau, iv, df_hat, cp=1 if key.cp == "C" else -1)
    return float(abs(g.delta / df_hat))


def tested_side(
    cfg: DefenseConfig,
    view: MarketView,
    short_put: OptionKey,
    short_call: OptionKey,
    position_pnl_dollars: float | None,
    r_dollars: float,
    at_session_close: bool,
) -> str | None:
    """Which side (if any) trips the trigger on this bar."""
    if cfg.trigger == "none":
        return None
    if cfg.trigger in ("touch", "close_beyond"):
        if cfg.trigger == "close_beyond" and not at_session_close:
            return None
        # touch uses the day's running extremes so a spike between snapshots
        # still counts (index level, not an order book — PLAN §14).
        low = view.today_low if cfg.trigger == "touch" else view.spot
        high = view.today_high if cfg.trigger == "touch" else view.spot
        if low <= short_put.strike:
            return "put"
        if high >= short_call.strike:
            return "call"
        return None
    if cfg.trigger == "short_delta":
        d_put = leg_abs_delta(view, short_put)
        d_call = leg_abs_delta(view, short_call)
        if d_put is not None and d_put >= cfg.trigger_delta:
            return "put"
        if d_call is not None and d_call >= cfg.trigger_delta:
            return "call"
        return None
    if cfg.trigger == "pnl_floor":
        if position_pnl_dollars is None or r_dollars <= 0:
            return None
        if position_pnl_dollars <= -cfg.trigger_pnl_frac * r_dollars:
            mid_strike = (short_put.strike + short_call.strike) / 2.0
            return "put" if view.spot < mid_strike else "call"
        return None
    raise ValueError(cfg.trigger)


def next_weekly_expiry(view: MarketView, after: dt.date) -> dt.date | None:
    weeklies = sorted(e for e, root, _ in view.expiries() if root == "SPXW" and e > after)
    return weeklies[0] if weeklies else None


def strike_at_delta(view: MarketView, expiry: dt.date, cp: str, target: float) -> float | None:
    from options_strategy.strategy.diagonal import _strike_by_delta

    return _strike_by_delta(view, expiry, cp, target)


def action_legs(
    cfg: DefenseConfig,
    side: str,
    view: MarketView,
    legs: tuple[tuple[OptionKey, int], ...],
) -> tuple[tuple[OptionKey, int], ...] | None:
    """Immediate-order legs for the configured action; None = not executable
    (e.g., no listed roll target) or handled elsewhere (nothing/delta_hedge)."""
    (sp, _), (sc, _), (lp, _), (lc, _) = legs
    short = sp if side == "put" else sc
    long_ = lp if side == "put" else lc
    cp = "P" if side == "put" else "C"

    if cfg.action in ("nothing", "delta_hedge"):
        return None
    if cfg.action == "close_tested_side":
        return ((short, +1), (long_, -1))
    if cfg.action == "buy_back_short":
        return ((short, +1),)
    if cfg.action == "close_all":
        return ((sp, +1), (sc, +1), (lp, -1), (lc, -1))
    if cfg.action == "roll_out":
        nxt = next_weekly_expiry(view, short.expiry)
        if nxt is None:
            return None
        return ((short, +1), (OptionKey("SPXW", nxt, short.strike, cp), -1))
    if cfg.action == "roll_out_away":
        nxt = next_weekly_expiry(view, short.expiry)
        if nxt is None:
            return None
        k = strike_at_delta(view, nxt, cp, cfg.roll_target_delta)
        if k is None:
            return None
        return ((short, +1), (OptionKey("SPXW", nxt, k, cp), -1))
    if cfg.action == "convert_vertical":
        k = strike_at_delta(view, long_.expiry, cp, cfg.roll_target_delta)
        if k is None or abs(k - long_.strike) < 1e-9:
            return None
        return ((short, +1), (OptionKey("SPXW", long_.expiry, k, cp), -1))
    raise ValueError(cfg.action)


def position_delta_dollars_per_point(
    view: MarketView, positions: dict[OptionKey, float]
) -> float | None:
    """Net position delta in $ per index point (for delta_hedge)."""
    total = 0.0
    for key, qty in positions.items():
        d = leg_abs_delta(view, key)
        if d is None:
            return None
        signed = d if key.cp == "C" else -d
        total += signed * qty * 100.0
    return total
