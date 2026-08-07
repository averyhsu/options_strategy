"""Performance metrics to IBKR PortfolioAnalyst conventions (PLAN §2.1).

Daily time-weighted returns (== NAV returns here: no external flows), VAMI
base 1000, sqrt(252) annualization, Sharpe/Sortino as excess-over-rf with a
configurable annual rf, max drawdown on close-to-close VAMI, downside
deviation vs the daily rf floor. Golden-tested against the reconstruction in
PLAN §2.1 (invariant §11.8): mean 0.47%/sigma 2.44%/dd 1.64% at rf 2.62%
must produce Sharpe 2.99 and Sortino 4.45.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

TRADING_DAYS = 252.0


@dataclass(frozen=True)
class IbkrMetrics:
    n_days: int
    mean_daily: float
    std_daily: float  # sample std (ddof=1)
    downside_dev_daily: float
    sharpe_ann: float
    sortino_ann: float
    max_dd: float
    dd_peak_idx: int
    dd_valley_idx: int
    recovery_days: int  # trading days valley -> prior peak regained; -1 if never
    pct_positive: float
    vami_final: float
    total_return: float


def daily_returns(nav: np.ndarray) -> np.ndarray:
    nav = np.asarray(nav, dtype=np.float64)
    return np.diff(nav) / nav[:-1]


def compute_metrics(returns: np.ndarray, rf_annual: float) -> IbkrMetrics:
    r = np.asarray(returns, dtype=np.float64)
    n = len(r)
    if n < 2:
        raise ValueError("need at least 2 daily returns")
    rf_daily = rf_annual / TRADING_DAYS

    mean = float(r.mean())
    std = float(r.std(ddof=1))
    downside = np.minimum(r - rf_daily, 0.0)
    # IBKR-style downside deviation: rf-floor shortfalls over ALL days
    dd_dev = float(np.sqrt(np.mean(downside**2)))

    sharpe = (mean - rf_daily) / std * np.sqrt(TRADING_DAYS) if std > 0 else 0.0
    sortino = (mean - rf_daily) / dd_dev * np.sqrt(TRADING_DAYS) if dd_dev > 0 else 0.0

    vami = 1000.0 * np.cumprod(1.0 + r)
    vami_full = np.concatenate([[1000.0], vami])
    cummax = np.maximum.accumulate(vami_full)
    dd_series = 1.0 - vami_full / cummax
    valley = int(np.argmax(dd_series))
    peak = int(np.argmax(vami_full[: valley + 1])) if valley > 0 else 0
    max_dd = float(dd_series[valley])
    recovery = -1
    if max_dd > 0:
        after = np.nonzero(vami_full[valley:] >= vami_full[peak])[0]
        recovery = int(after[0]) if len(after) else -1

    return IbkrMetrics(
        n_days=n,
        mean_daily=mean,
        std_daily=std,
        downside_dev_daily=dd_dev,
        sharpe_ann=float(sharpe),
        sortino_ann=float(sortino),
        max_dd=max_dd,
        dd_peak_idx=peak,
        dd_valley_idx=valley,
        recovery_days=recovery,
        pct_positive=float((r > 0).mean()),
        vami_final=float(vami_full[-1]),
        total_return=float(vami_full[-1] / 1000.0 - 1.0),
    )


@dataclass(frozen=True)
class Fingerprints:
    """The §2 fingerprint vector for a daily NAV window (+ weekly stats)."""

    sharpe_ann: float
    sortino_ann: float
    std_daily: float
    downside_dev_daily: float
    mean_daily: float
    pct_positive: float
    max_dd: float
    dd_peak_date: dt.date | None
    dd_valley_date: dt.date | None
    recovery_days: int
    weekly_wr: float
    median_win_pct_r: float
    log_vami: np.ndarray  # for curve-distance terms


def fingerprints(
    sessions: list[dt.date],
    nav: np.ndarray,
    rf_annual: float,
    weekly_pnls: np.ndarray | None = None,
    weekly_deployed: np.ndarray | None = None,
) -> Fingerprints:
    r = daily_returns(nav)
    m = compute_metrics(r, rf_annual)
    weekly_wr = float("nan")
    median_win = float("nan")
    if weekly_pnls is not None and len(weekly_pnls):
        wins = weekly_pnls > 0
        weekly_wr = float(wins.mean())
        if weekly_deployed is not None and wins.any():
            with np.errstate(invalid="ignore", divide="ignore"):
                mag = weekly_pnls[wins] / weekly_deployed[wins]
            mag = mag[np.isfinite(mag)]
            median_win = float(np.median(mag)) if len(mag) else float("nan")
    vami = 1000.0 * np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return Fingerprints(
        sharpe_ann=m.sharpe_ann,
        sortino_ann=m.sortino_ann,
        std_daily=m.std_daily,
        downside_dev_daily=m.downside_dev_daily,
        mean_daily=m.mean_daily,
        pct_positive=m.pct_positive,
        max_dd=m.max_dd,
        dd_peak_date=sessions[m.dd_peak_idx] if m.dd_peak_idx < len(sessions) else None,
        dd_valley_date=sessions[m.dd_valley_idx] if m.dd_valley_idx < len(sessions) else None,
        recovery_days=m.recovery_days,
        weekly_wr=weekly_wr,
        median_win_pct_r=median_win,
        log_vami=np.log(vami),
    )
