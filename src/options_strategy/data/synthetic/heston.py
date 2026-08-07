"""Heston + Merton-jump underlying path on the session/minute grid (PLAN §5).

Full-truncation Euler; 1-min RTH steps plus a single overnight step per session
gap (weekend/holiday gaps get extra variance and an occasional jump). Forced
events REPLACE the stochastic overnight step so scripted gaps land exactly.
Deterministic for a fixed config: one RNG stream, fixed draw order.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from options_strategy.data.synthetic.config import SyntheticWorldConfig

_STREAM_PATH = 0

TRADING_DAYS = 252.0
FULL_SESSION_BARS = 390  # 09:30 -> 16:00


@dataclass(frozen=True)
class UnderlyingPath:
    """Per-bar arrays (bar-START timestamps, ET-naive datetime64) plus session slices."""

    ts: np.ndarray  # datetime64[us], ET wall time (naive; localized on write)
    s: np.ndarray  # float64 index level at bar close
    v: np.ndarray  # float64 instantaneous variance at bar close
    session_dates: np.ndarray  # datetime64[D], one per session
    session_start_idx: np.ndarray  # int64, index of first bar of each session
    session_n_bars: np.ndarray  # int64

    def session_slice(self, i: int) -> slice:
        a = int(self.session_start_idx[i])
        return slice(a, a + int(self.session_n_bars[i]))

    def daily_frame(self) -> pl.DataFrame:
        opens, highs, lows, closes = [], [], [], []
        for i in range(len(self.session_dates)):
            sl = self.session_slice(i)
            seg = self.s[sl]
            opens.append(seg[0])
            highs.append(seg.max())
            lows.append(seg.min())
            closes.append(seg[-1])
        return pl.DataFrame(
            {
                "session": self.session_dates,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
            }
        )


def _per_session_regime(
    cfg: SyntheticWorldConfig, n_sessions: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = np.empty(n_sessions)
    theta_mult = np.empty(n_sessions)
    lam_mult = np.empty(n_sessions)
    i = 0
    for seg in cfg.segments:
        j = min(i + seg.length_sessions, n_sessions)
        mu[i:j] = seg.mu_annual
        theta_mult[i:j] = seg.theta_mult
        lam_mult[i:j] = seg.lam_mult
        i = j
        if i >= n_sessions:
            break
    if i < n_sessions:  # last segment extends
        mu[i:] = cfg.segments[-1].mu_annual
        theta_mult[i:] = cfg.segments[-1].theta_mult
        lam_mult[i:] = cfg.segments[-1].lam_mult
    return mu, theta_mult, lam_mult


def simulate(cfg: SyntheticWorldConfig, sessions: pl.DataFrame) -> UnderlyingPath:
    """sessions: schema per data.schemas.SESSIONS_SCHEMA, already date-filtered."""
    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, _STREAM_PATH]))
    h, on = cfg.heston, cfg.overnight
    forced = {ev.session: ev for ev in cfg.forced_events}

    session_dates = sessions["session"].to_numpy()
    opens = sessions["open_et"].dt.replace_time_zone(None).to_numpy()
    closes = sessions["close_et"].dt.replace_time_zone(None).to_numpy()
    n_sessions = len(session_dates)
    mu_s, theta_mult_s, lam_mult_s = _per_session_regime(cfg, n_sessions)

    step = np.timedelta64(cfg.underlying_step_minutes, "m")
    minutes_per_bar = float(cfg.underlying_step_minutes)
    dt_bar = (1.0 - on.overnight_var_frac) / TRADING_DAYS * (minutes_per_bar / FULL_SESSION_BARS)

    ts_chunks: list[np.ndarray] = []
    n_bars = np.empty(n_sessions, dtype=np.int64)
    for i in range(n_sessions):
        grid = np.arange(opens[i], closes[i], step, dtype="datetime64[us]")
        ts_chunks.append(grid)
        n_bars[i] = len(grid)
    start_idx = np.concatenate([[0], np.cumsum(n_bars)[:-1]])
    ts = np.concatenate(ts_chunks)

    total = int(n_bars.sum())
    s_out = np.empty(total)
    v_out = np.empty(total)

    log_s = float(np.log(cfg.s0))
    v = float(h.v0)
    sq1m_rho2 = float(np.sqrt(1.0 - h.rho**2))

    for i in range(n_sessions):
        theta_eff = h.theta * theta_mult_s[i]
        lam_eff = cfg.jumps.lam_per_year * lam_mult_s[i]
        mu = mu_s[i]

        if i > 0:
            gap_days = int(
                (session_dates[i] - session_dates[i - 1]).astype("timedelta64[D]")
                // np.timedelta64(1, "D")
            )
            ev = forced.get(session_dates[i].astype("datetime64[D]").astype(object))
            if ev is not None:
                log_s += float(np.log1p(ev.gap_pct))
                v = max(v * ev.vol_mult, 0.0)
            else:
                dt_on = (
                    on.overnight_var_frac + max(gap_days - 1, 0) * on.extra_day_var_frac
                ) / TRADING_DAYS
                z1, z2 = rng.standard_normal(2)
                zs = h.rho * z1 + sq1m_rho2 * z2
                vp = max(v, 0.0)
                log_s += (mu - 0.5 * vp) * dt_on + np.sqrt(vp * dt_on) * zs
                v = v + h.kappa * (theta_eff - vp) * dt_on + h.xi * np.sqrt(vp * dt_on) * z1
                if gap_days >= 3 and rng.random() < on.weekend_jump_prob:
                    log_s += rng.normal(on.weekend_jump_mean, on.weekend_jump_sigma)

        nb = int(n_bars[i])
        z1v = rng.standard_normal(nb)
        z2v = rng.standard_normal(nb)
        jump_u = rng.random(nb)
        jump_z = rng.standard_normal(nb)
        p_jump = lam_eff * dt_bar
        sl = start_idx[i]
        for b in range(nb):
            vp = max(v, 0.0)
            zs = h.rho * z1v[b] + sq1m_rho2 * z2v[b]
            log_s += (mu - 0.5 * vp) * dt_bar + np.sqrt(vp * dt_bar) * zs
            if jump_u[b] < p_jump:
                log_s += cfg.jumps.mean + cfg.jumps.sigma * jump_z[b]
            v = v + h.kappa * (theta_eff - vp) * dt_bar + h.xi * np.sqrt(vp * dt_bar) * z1v[b]
            s_out[sl + b] = np.exp(log_s)
            v_out[sl + b] = max(v, 0.0)

    return UnderlyingPath(
        ts=ts,
        s=s_out,
        v=v_out,
        session_dates=session_dates.astype("datetime64[D]"),
        session_start_idx=start_idx,
        session_n_bars=n_bars,
    )
