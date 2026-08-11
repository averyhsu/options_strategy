"""Double-diagonal builder (PLAN §8.1): short front-week strangle + long
further-dated wings, strikes picked by target delta on the live chain (or
fully hand-specified via `explicit` for golden tests).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict

from options_strategy.engine.instruments import OptionKey
from options_strategy.engine.margin import LegState
from options_strategy.engine.marketview import MarketView
from options_strategy.pricing.greeks import greeks
from options_strategy.pricing.iv import implied_vol
from options_strategy.strategy.bands import above_ema_next_returns, band_edges


class ExplicitLegs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    front_expiry: dt.date
    back_put_expiry: dt.date
    back_call_expiry: dt.date
    short_put: float
    short_call: float
    long_put: float
    long_call: float


STRIKE_FAMILIES = ("percentile", "delta")


class StructureConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # DEFAULT family (PLAN §8.1, 2026-08-10 amendment): short strikes at
    # spot x (1 + edge) where edges are quantiles of the trailing above-EMA
    # weekly-return distribution — the only rule the author's candles-only
    # backtest could have produced. "delta" is the fallback family.
    strike_family: str = "percentile"
    coverage_q_put: float = 0.90  # one-sided coverage, prior 0.80..0.95
    coverage_q_call: float = 0.90
    band_ema_len: int = 21  # sweep ties this to the regime ema_len dim
    min_band_obs: int = 52  # skip entry until this many above-EMA weeks exist

    short_put_delta: float = 0.20  # abs undiscounted forward delta target
    short_call_delta: float = 0.15
    long_put_expiry_offset_days: int = 21  # min calendar days beyond front
    long_call_expiry_offset_days: int = 21
    long_strike_offset: float = 25.0  # points beyond the short strike
    front_min_days: int = 5
    front_max_days: int = 9
    # §8.1 net_position: "credit required?" is itself sweepable. When True the
    # structure must price as a net credit and entry thresholds gate on it;
    # when False debit diagonals are tradeable and credit gates are skipped.
    require_credit: bool = True
    min_credit_frac: float = 0.10  # net credit >= frac * reference width
    explicit: ExplicitLegs | None = None

    def model_post_init(self, __context) -> None:
        if self.strike_family not in STRIKE_FAMILIES:
            raise ValueError(f"strike_family {self.strike_family!r} not in {STRIKE_FAMILIES}")


@dataclass(frozen=True)
class DiagonalPlan:
    legs: tuple[tuple[OptionKey, int], ...]  # ((SP,-1),(SC,-1),(LP,+1),(LC,+1))
    mid_credit: float  # positive = credit at current mids (points)
    reference_width: float  # max wing width (points)
    leg_states: tuple[LegState, ...]  # for sizing / risk

    @property
    def short_put(self) -> OptionKey:
        return self.legs[0][0]

    @property
    def short_call(self) -> OptionKey:
        return self.legs[1][0]


def _chain_side(view: MarketView, expiry: dt.date, cp: str) -> pl.DataFrame:
    return (
        view.chain(root="SPXW", expiry=expiry)
        .filter((pl.col("cp") == cp) & (pl.col("bid") > 0))
        .with_columns(mid=(pl.col("bid") + pl.col("ask")) / 2.0)
        .sort("strike")
    )


def _strike_by_delta(
    view: MarketView, expiry: dt.date, cp: str, target_abs_delta: float
) -> float | None:
    fit = view.forward("SPXW", expiry)
    if fit is None:
        return None
    f_hat, df_hat, tau = fit
    side = _chain_side(view, expiry, cp)
    otm = side.filter(pl.col("strike") < f_hat if cp == "P" else pl.col("strike") > f_hat)
    if otm.height < 2:
        return None
    k = otm["strike"].to_numpy()
    iv = implied_vol(otm["mid"].to_numpy(), f_hat, k, tau, df_hat, cp=1 if cp == "C" else -1)
    good = np.isfinite(iv)
    if good.sum() < 2:
        return None
    g = greeks(f_hat, k[good], tau, iv[good], df_hat, cp=1 if cp == "C" else -1)
    abs_delta = np.abs(g.delta / df_hat)  # undiscounted N(d1)-style delta
    idx = int(np.argmin(np.abs(abs_delta - target_abs_delta)))
    return float(k[good][idx])


def _nearest_listed(view: MarketView, expiry: dt.date, cp: str, target: float) -> float | None:
    side = _chain_side(view, expiry, cp)
    if side.height == 0:
        return None
    strikes = side["strike"].to_numpy()
    return float(strikes[int(np.argmin(np.abs(strikes - target)))])


def _mid(view: MarketView, key: OptionKey) -> float | None:
    q = view.quote(key)
    if q is None or not q.sane or q.bid <= 0:
        return None
    return (q.bid + q.ask) / 2.0


def _leg_state(view: MarketView, key: OptionKey, ratio: int) -> LegState | None:
    mid = _mid(view, key)
    fit = view.forward(key.root, key.expiry)
    if mid is None or fit is None:
        return None
    f_hat, df_hat, tau = fit
    iv = float(implied_vol(mid, f_hat, key.strike, tau, df_hat, cp=1 if key.cp == "C" else -1))
    if not np.isfinite(iv):
        return None
    return LegState(key=key, ratio=ratio, mid=mid, iv=iv, tau=tau, forward=f_hat, df=df_hat)


def select_expiries(
    view: MarketView, cfg: StructureConfig
) -> tuple[dt.date, dt.date, dt.date] | None:
    """(front, back_put, back_call) SPXW expiries per the offsets."""
    weeklies = sorted(e for e, root, _ in view.expiries() if root == "SPXW")
    today = view.session_date
    front = next(
        (e for e in weeklies if cfg.front_min_days <= (e - today).days <= cfg.front_max_days),
        None,
    )
    if front is None:
        return None
    back_put = next(
        (e for e in weeklies if (e - front).days >= cfg.long_put_expiry_offset_days), None
    )
    back_call = next(
        (e for e in weeklies if (e - front).days >= cfg.long_call_expiry_offset_days), None
    )
    if back_put is None or back_call is None:
        return None
    return front, back_put, back_call


def build_diagonal(view: MarketView, cfg: StructureConfig) -> DiagonalPlan | None:
    if cfg.explicit is not None:
        ex = cfg.explicit
        keys = (
            (OptionKey("SPXW", ex.front_expiry, ex.short_put, "P"), -1),
            (OptionKey("SPXW", ex.front_expiry, ex.short_call, "C"), -1),
            (OptionKey("SPXW", ex.back_put_expiry, ex.long_put, "P"), +1),
            (OptionKey("SPXW", ex.back_call_expiry, ex.long_call, "C"), +1),
        )
    else:
        expiries = select_expiries(view, cfg)
        if expiries is None:
            return None
        front, back_put, back_call = expiries
        if cfg.strike_family == "percentile":
            arr = above_ema_next_returns(view.daily_history(), cfg.band_ema_len)
            edges = band_edges(arr, cfg.coverage_q_put, cfg.coverage_q_call, cfg.min_band_obs)
            if edges is None:
                return None
            sp = _nearest_listed(view, front, "P", view.spot * (1.0 + edges[0]))
            sc = _nearest_listed(view, front, "C", view.spot * (1.0 + edges[1]))
        else:
            sp = _strike_by_delta(view, front, "P", cfg.short_put_delta)
            sc = _strike_by_delta(view, front, "C", cfg.short_call_delta)
        if sp is None or sc is None or sp >= sc:
            return None
        lp = _nearest_listed(view, back_put, "P", sp - cfg.long_strike_offset)
        lc = _nearest_listed(view, back_call, "C", sc + cfg.long_strike_offset)
        if lp is None or lc is None:
            return None
        keys = (
            (OptionKey("SPXW", front, sp, "P"), -1),
            (OptionKey("SPXW", front, sc, "C"), -1),
            (OptionKey("SPXW", back_put, lp, "P"), +1),
            (OptionKey("SPXW", back_call, lc, "C"), +1),
        )

    states = []
    for key, ratio in keys:
        st = _leg_state(view, key, ratio)
        if st is None:
            return None
        states.append(st)
    mid_credit = -sum(s.ratio * s.mid for s in states)
    width = max(
        abs(keys[0][0].strike - keys[2][0].strike),
        abs(keys[1][0].strike - keys[3][0].strike),
    )
    return DiagonalPlan(
        legs=keys,
        mid_credit=mid_credit,
        reference_width=width,
        leg_states=tuple(states),
    )
