"""Daily P&L attribution (invariant §11.5): a first-order Taylor explanation
delta*dF + 0.5*gamma*dF^2 + theta*dt + vega*dsigma must explain actual mark
moves within tolerance on non-gap days; gap days are reported, not excused.
"""

from __future__ import annotations

from dataclasses import dataclass

from options_strategy.pricing.greeks import greeks


@dataclass(frozen=True)
class PositionDay:
    """State of one option position at a mark (index points / years)."""

    forward: float
    strike: float
    tau: float
    iv: float
    df: float
    cp: int  # +1 / -1
    mark: float


@dataclass(frozen=True)
class Attribution:
    actual: float  # mark move, index points per contract
    explained: float
    residual: float
    is_gap_day: bool


def explain_day(prev: PositionDay, curr: PositionDay, gap_threshold: float = 0.015) -> Attribution:
    g = greeks(prev.forward, prev.strike, prev.tau, prev.iv, prev.df, cp=prev.cp)
    d_f = curr.forward - prev.forward
    d_sigma = curr.iv - prev.iv
    d_t = prev.tau - curr.tau  # positive as time passes
    explained = (
        float(g.delta) * d_f
        + 0.5 * float(g.gamma) * d_f * d_f
        + float(g.vega) * d_sigma
        + float(g.theta) * d_t
    )
    actual = curr.mark - prev.mark
    return Attribution(
        actual=actual,
        explained=explained,
        residual=actual - explained,
        is_gap_day=abs(d_f) / prev.forward > gap_threshold,
    )
