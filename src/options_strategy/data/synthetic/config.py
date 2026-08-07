"""Synthetic world configuration (PLAN §5). All fields sweepable via YAML."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from options_strategy.data.calendar import ExpiryRules


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HestonParams(_Frozen):
    v0: float = 0.03
    theta: float = 0.03
    kappa: float = 2.0
    xi: float = 0.5
    rho: float = -0.7


class JumpParams(_Frozen):
    lam_per_year: float = 0.5
    mean: float = -0.03
    sigma: float = 0.04


class OvernightParams(_Frozen):
    # Fraction of a day's variance realized overnight vs. during RTH.
    overnight_var_frac: float = 0.25
    # Additional variance per extra calendar day of a weekend/holiday gap.
    extra_day_var_frac: float = 0.10
    weekend_jump_prob: float = 0.03
    weekend_jump_mean: float = -0.02
    weekend_jump_sigma: float = 0.03


class ScenarioSegment(_Frozen):
    """Piecewise regime script: consecutive segments cover the date range."""

    length_sessions: int  # last segment may exceed the remaining range
    mu_annual: float = 0.06  # annualized log-drift
    theta_mult: float = 1.0
    lam_mult: float = 1.0


class ForcedEvent(_Frozen):
    """Deterministic overnight event: REPLACES the stochastic overnight step
    into `session` with an exact gap and variance shock (testable to the tick).
    """

    session: dt.date
    gap_pct: float  # open = prior close * (1 + gap_pct)
    vol_mult: float = 1.0  # v_open = v_prior_close * vol_mult


class RatesParams(_Frozen):
    base_rate: float = 0.0262  # continuously-compounded zero, flat
    div_yield: float = 0.013


class SurfaceParams(_Frozen):
    """SSVI (Gatheral-Jacquier): w(k) = theta/2 * (1 + rho*phi*k + sqrt((phi*k+rho)^2 + 1-rho^2)),
    phi = eta / theta^gamma_. theta_T comes from Heston expected integrated variance."""

    rho: float = -0.7
    eta: float = 0.8
    gamma_: float = 0.5


class MicrostructureParams(_Frozen):
    half_width_frac: float = 0.006  # proportional component of half-spread
    half_width_abs: float = 0.10  # additive component ($)
    min_half_width: float = 0.025
    wing_widen: float = 0.35  # * normalized |moneyness|
    stress_widen: float = 1.5  # * max(v/theta - 1, 0)
    size_median: float = 40.0
    size_sigma: float = 0.9
    stale_rate: float = 0.0  # fraction of (option, intraday-session) pairs frozen
    stale_minutes: int = 45
    # Freeze only options a stale detector can legitimately see: present every
    # bar of the session and liquid enough (mid >= this) throughout.
    stale_target_min_mid: float = 0.75
    crossed_rate: float = 0.0  # fraction of quote rows made crossed
    locked_rate: float = 0.0


class ChainParams(_Frozen):
    strike_step_near: float = 5.0
    strike_step_far: float = 25.0
    near_band_pct: float = 0.06  # +/- band around spot on the 5-point grid
    span_pct: float = 0.20  # full half-span of the listed grid
    n_weeklies: int = 9
    n_monthlies: int = 3


class SnapshotSpec(_Frozen):
    eod: bool = True  # daily snapshot at the last RTH bar
    intraday_windows: tuple[tuple[dt.date, dt.date], ...] = ()


class SyntheticWorldConfig(_Frozen):
    name: str
    seed: int = 20260806
    start: dt.date
    end: dt.date
    underlying_step_minutes: int = 1
    s0: float = 5000.0
    heston: HestonParams = HestonParams()
    jumps: JumpParams = JumpParams()
    overnight: OvernightParams = OvernightParams()
    segments: tuple[ScenarioSegment, ...] = (ScenarioSegment(length_sessions=10_000),)
    forced_events: tuple[ForcedEvent, ...] = ()
    rates: RatesParams = RatesParams()
    surface: SurfaceParams = SurfaceParams()
    micro: MicrostructureParams = MicrostructureParams()
    chain: ChainParams = ChainParams()
    snapshots: SnapshotSpec = SnapshotSpec()
    expiry_rules: ExpiryRules = ExpiryRules()

    @field_validator("name")
    @classmethod
    def _name_labels_synthetic(cls, v: str) -> str:
        if "synthetic" not in v.lower():
            raise ValueError("synthetic world names must contain 'synthetic' (labeling rule)")
        return v

    @model_validator(mode="after")
    def _range_ok(self) -> SyntheticWorldConfig:
        if self.end < self.start:
            raise ValueError("end < start")
        if not self.segments:
            raise ValueError("at least one scenario segment required")
        for ev in self.forced_events:
            if not (self.start <= ev.session <= self.end):
                raise ValueError(f"forced event {ev.session} outside [start, end]")
        return self

    @property
    def data_version(self) -> str:
        from options_strategy.config import short_hash

        return f"synthetic-{short_hash(self)}"
