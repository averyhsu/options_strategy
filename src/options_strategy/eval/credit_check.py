"""Mini-slice credit check (PLAN §1.6 2026-08-16 amendment, dual reading).

For each sample date x structure the check reports BOTH readings of the
author's "+30% of risk" claim — it must NOT hard-fail debit structures:

(a) signed net premium as % of risk (positive = credit) — the credit reading;
(b) for debits, max-gain / risk at front expiry within the short-strike band,
    and whether +30% of R is achievable there — the return-on-risk reading
    (near-calendar wings make debits the structurally expected case).

A near-ATM reference structure (shorts at / just outside spot) is priced on
every sample date alongside the band-edge q-levels: the author's "big credit
only happens if it is ATM or ITM" line makes that the direct Branch-B revenue
measurement.

Back legs at front expiry are valued with Black-76 at each leg's CURRENT
per-strike IV (sticky-strike), tau reduced by the front tenor — the same
carry/df treatment as margin.scenario_extremes. Runs identically on synthetic
worlds (validation now) and on the vendor slice when it lands in
data/raw/cboe/ (a chain frame + parity forward fits is all it needs).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass

import numpy as np
import polars as pl

from options_strategy.pricing import black76
from options_strategy.pricing.iv import implied_vol

RISK_FLOOR_POINTS = 0.05  # avoid div-by-zero on degenerate zero-risk packages
CLAIM_RETURN_ON_RISK = 0.30
DEFAULT_WING_OFFSETS = (0.0, 25.0, 50.0)
DEFAULT_BACK_OFFSET_DAYS = 21

Leg = tuple[dt.date, str, float, int]  # (expiry, cp, strike, ratio)


@dataclass(frozen=True)
class StructureMetrics:
    label: str  # "q90", "atm_ref", ...
    wing_offset: float
    short_put: float
    short_call: float
    long_put: float
    long_call: float
    front_expiry: dt.date
    back_expiry: dt.date
    net_premium: float  # signed, points; positive = CREDIT
    front_premium: float  # front strangle premium collected (the revenue side)
    risk_points: float  # max wing width + net debit (floored)
    net_premium_pct_risk: float  # reading (a)
    is_debit: bool
    max_gain_pct_risk: float  # reading (b): max gain in band at front expiry / risk
    thirty_pct_achievable: bool  # reading (b) vs the +30%-of-R claim


def _side(chain: pl.DataFrame, expiry: dt.date, cp: str) -> pl.DataFrame:
    return chain.filter(
        (pl.col("expiry_date") == expiry) & (pl.col("cp") == cp) & (pl.col("bid") > 0)
    ).sort("strike")


def _mid(chain: pl.DataFrame, expiry: dt.date, cp: str, strike: float) -> float | None:
    row = _side(chain, expiry, cp).filter(pl.col("strike") == strike)
    if row.height == 0:
        return None
    return float((row["bid"][0] + row["ask"][0]) / 2.0)


def _nearest(chain: pl.DataFrame, expiry: dt.date, cp: str, target: float) -> float | None:
    side = _side(chain, expiry, cp)
    if side.height == 0:
        return None
    strikes = side["strike"].to_numpy()
    return float(strikes[int(np.argmin(np.abs(strikes - target)))])


def _value_at_front_expiry(
    legs: list[Leg],
    mids: dict[Leg, float],
    s_grid: np.ndarray,
    spot: float,
    fits: dict[dt.date, tuple[float, float, float]],
    front_expiry: dt.date,
) -> np.ndarray:
    """Position value (points) at front expiry across an S grid: expiring legs
    at intrinsic, later legs via Black-76 at their current sticky-strike IV."""
    front_tau = fits[front_expiry][2]
    total = np.zeros(len(s_grid))
    for leg in legs:
        expiry, cp, strike, ratio = leg
        w = 1 if cp == "C" else -1
        if expiry == front_expiry:
            total += ratio * np.maximum(w * (s_grid - strike), 0.0)
            continue
        f_hat, df_hat, tau = fits[expiry]
        iv = float(implied_vol(mids[leg], f_hat, strike, tau, df_hat, cp=w))
        if not np.isfinite(iv):
            iv = 1e-4  # unpriceable wing: value at intrinsic-forward
        tau_left = max(tau - front_tau, 1e-9)
        carry = math.log(f_hat / spot) / tau
        f_prime = s_grid * math.exp(carry * tau_left)
        r_rate = -math.log(df_hat) / tau if df_hat > 0 else 0.0
        df_prime = math.exp(-r_rate * tau_left)
        total += ratio * black76.price(f_prime, strike, tau_left, iv, df_prime, cp=w)
    return total


def structure_metrics(
    chain: pl.DataFrame,
    spot: float,
    fits: dict[dt.date, tuple[float, float, float]],
    front_expiry: dt.date,
    back_expiry: dt.date,
    put_target: float,
    call_target: float,
    wing_offset: float,
    label: str,
    n_grid: int = 41,
) -> StructureMetrics | None:
    sp = _nearest(chain, front_expiry, "P", put_target)
    sc = _nearest(chain, front_expiry, "C", call_target)
    if sp is None or sc is None or sp > sc:
        return None
    lp = _nearest(chain, back_expiry, "P", sp - wing_offset)
    lc = _nearest(chain, back_expiry, "C", sc + wing_offset)
    if lp is None or lc is None:
        return None
    legs: list[Leg] = [
        (front_expiry, "P", sp, -1),
        (front_expiry, "C", sc, -1),
        (back_expiry, "P", lp, +1),
        (back_expiry, "C", lc, +1),
    ]
    mids: dict[Leg, float] = {}
    for leg in legs:
        m = _mid(chain, leg[0], leg[1], leg[2])
        if m is None:
            return None
        mids[leg] = m
    if front_expiry not in fits or back_expiry not in fits:
        return None

    net_premium = -sum(leg[3] * mids[leg] for leg in legs)
    front_premium = sum(mids[leg] for leg in legs if leg[0] == front_expiry)
    net_debit = -net_premium
    width = max(abs(sp - lp), abs(sc - lc))
    risk_points = max(width + net_debit, RISK_FLOOR_POINTS)

    s_grid = np.linspace(sp, sc, n_grid)
    value = _value_at_front_expiry(legs, mids, s_grid, spot, fits, front_expiry)
    max_gain = float(np.max(value) - net_debit)
    max_gain_pct = max_gain / risk_points
    return StructureMetrics(
        label=label,
        wing_offset=wing_offset,
        short_put=sp,
        short_call=sc,
        long_put=lp,
        long_call=lc,
        front_expiry=front_expiry,
        back_expiry=back_expiry,
        net_premium=net_premium,
        front_premium=front_premium,
        risk_points=risk_points,
        net_premium_pct_risk=net_premium / risk_points,
        is_debit=net_premium < 0,
        max_gain_pct_risk=max_gain_pct,
        thirty_pct_achievable=max_gain_pct >= CLAIM_RETURN_ON_RISK,
    )


def _atm_targets(chain: pl.DataFrame, front: dt.date, spot: float) -> tuple[float, float] | None:
    """Shorts at / just OUTSIDE spot (first put strike <= spot, first call >= spot)."""
    puts = _side(chain, front, "P").filter(pl.col("strike") <= spot)
    calls = _side(chain, front, "C").filter(pl.col("strike") >= spot)
    if puts.height == 0 or calls.height == 0:
        return None
    return float(puts["strike"][-1]), float(calls["strike"][0])


def run_credit_check(
    chain: pl.DataFrame,
    spot: float,
    fits: dict[dt.date, tuple[float, float, float]],
    session: dt.date,
    band_edges: dict[str, tuple[float, float]],
    wing_offsets: tuple[float, ...] = DEFAULT_WING_OFFSETS,
    front_dte_window: tuple[int, int] = (5, 9),
    back_offset_days: int = DEFAULT_BACK_OFFSET_DAYS,
) -> pl.DataFrame:
    """All structures for one sample date. `band_edges` maps label ->
    (put_edge_ret, call_edge_ret), e.g. from the candle study's (b) table;
    a near-ATM reference is always added."""
    expiries = sorted({e for e in chain["expiry_date"].unique().to_list() if e in fits})
    lo, hi = front_dte_window
    front = next((e for e in expiries if lo <= (e - session).days <= hi), None)
    if front is None:
        return pl.DataFrame()
    back = next((e for e in expiries if (e - front).days >= back_offset_days), None)
    if back is None:
        return pl.DataFrame()

    rows = []
    targets: list[tuple[str, float, float]] = [
        (label, spot * (1.0 + pe), spot * (1.0 + ce)) for label, (pe, ce) in band_edges.items()
    ]
    atm = _atm_targets(chain, front, spot)
    if atm is not None:
        targets.append(("atm_ref", atm[0], atm[1]))
    for label, put_t, call_t in targets:
        for off in wing_offsets:
            m = structure_metrics(chain, spot, fits, front, back, put_t, call_t, off, label)
            if m is not None:
                rows.append({"session": session, **asdict(m)})
    return pl.DataFrame(rows)
