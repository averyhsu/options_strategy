"""Risk-based sizing: three operational definitions of "risk per combo"
(PLAN §7.4), all sweepable. Dollars per 1 combo; n = floor(frac * NAV / R).

- r_scenario (default): worst loss revaluing the combo AT THE FRONT EXPIRY
  over S in +/-12% (0.5% steps) x relative vol shifts {-30%, 0, +30%}. Front
  legs go to intrinsic; back legs reprice under sticky-strike IVs (PLAN §6
  vol-dynamics assumption) with the vol shift applied multiplicatively.
- r_width: distance proxy — max same-cp short-to-long strike width minus the
  net credit received.
- r_margin: Reg-T-ish defined-risk spread margin — max side width (no credit
  offset), used as constraint and alternative denominator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from options_strategy.engine import CONTRACT_MULTIPLIER
from options_strategy.engine.instruments import OptionKey
from options_strategy.pricing import black76


@dataclass(frozen=True)
class ScenarioGrid:
    s_range: float = 0.12
    s_step: float = 0.005
    vol_shifts: tuple[float, ...] = (-0.30, 0.0, 0.30)


@dataclass(frozen=True)
class LegState:
    """Everything needed to revalue one leg."""

    key: OptionKey
    ratio: int  # signed, per combo
    mid: float  # current value (index points)
    iv: float  # current implied vol at this strike
    tau: float  # years to ITS settlement
    forward: float
    df: float


def r_scenario(legs: list[LegState], spot: float, grid: ScenarioGrid | None = None) -> float:
    """Worst dollar loss per combo at the front expiry over the scenario grid."""
    grid = grid or ScenarioGrid()
    front_tau = min(leg.tau for leg in legs)
    entry_debit = sum(leg.ratio * leg.mid for leg in legs)

    s_mults = np.arange(-grid.s_range, grid.s_range + grid.s_step / 2, grid.s_step)
    worst_pnl = 0.0
    for s_mult in s_mults:
        s_prime = spot * (1.0 + s_mult)
        for vshift in grid.vol_shifts:
            value = 0.0
            for leg in legs:
                w = 1 if leg.key.cp == "C" else -1
                tau_left = leg.tau - front_tau
                if tau_left <= 1e-9:
                    value += leg.ratio * max(w * (s_prime - leg.key.strike), 0.0)
                else:
                    carry = math.log(leg.forward / spot) / leg.tau  # (r - q) proxy
                    f_prime = s_prime * math.exp(carry * tau_left)
                    r_rate = -math.log(leg.df) / leg.tau if leg.df > 0 else 0.0
                    df_prime = math.exp(-r_rate * tau_left)
                    iv_prime = max(leg.iv * (1.0 + vshift), 1e-4)
                    value += leg.ratio * float(
                        black76.price(f_prime, leg.key.strike, tau_left, iv_prime, df_prime, cp=w)
                    )
            pnl = (value - entry_debit) * CONTRACT_MULTIPLIER
            worst_pnl = min(worst_pnl, pnl)
    return max(-worst_pnl, 0.0)


def r_width(legs: list[LegState]) -> float:
    """Max same-cp short->long width minus net credit, per combo, in dollars."""
    entry_debit = sum(leg.ratio * leg.mid for leg in legs)
    width = 0.0
    for cp in ("C", "P"):
        shorts = [leg for leg in legs if leg.key.cp == cp and leg.ratio < 0]
        longs = [leg for leg in legs if leg.key.cp == cp and leg.ratio > 0]
        for s_leg in shorts:
            if longs:
                nearest = min(longs, key=lambda x: abs(x.key.strike - s_leg.key.strike))
                width = max(width, abs(nearest.key.strike - s_leg.key.strike))
            else:
                raise ValueError(f"naked short {s_leg.key} has no width — use r_scenario")
    return max((width + entry_debit) * CONTRACT_MULTIPLIER, 0.0)


def r_margin(legs: list[LegState]) -> float:
    """Reg-T-ish spread margin: max side width in dollars, no credit offset."""
    width = 0.0
    for cp in ("C", "P"):
        shorts = [leg for leg in legs if leg.key.cp == cp and leg.ratio < 0]
        longs = [leg for leg in legs if leg.key.cp == cp and leg.ratio > 0]
        for s_leg in shorts:
            if not longs:
                raise ValueError(f"naked short {s_leg.key} — margin model needs a wing")
            nearest = min(longs, key=lambda x: abs(x.key.strike - s_leg.key.strike))
            width = max(width, abs(nearest.key.strike - s_leg.key.strike))
    return width * CONTRACT_MULTIPLIER


def contracts_for_risk(risk_fraction: float, nav: float, r_per_combo: float) -> int:
    """n = floor(frac * NAV / R); zero when R is degenerate."""
    if r_per_combo <= 0:
        return 0
    return max(math.floor(risk_fraction * nav / r_per_combo), 0)
