"""Trading sessions and era-correct SPX/SPXW expiry listing.

Sessions come from exchange_calendars XNYS as a CBOE proxy (see ASSUMPTIONS.md:
exchange_calendars ships no CBOE index-options calendar; SPX trading days
follow the NYSE holiday schedule, early closes included).

Expiry listing here is a RULE SET, not history: the synthetic world builds its
listed-expiry table from these rules, and everything downstream trusts that
table. For real data (Pass 2) the observed expiry table from the vendor wins
(PLAN §3.2). Era defaults follow PLAN §4.3/§14: Friday weeklies throughout,
Monday/Wednesday from 2016, Tuesday/Thursday only from mid-2022, AM-settled
SPX monthlies on third Fridays.

Holiday shift follows the CBOE convention: a Friday expiration (weekly or
monthly) on a holiday moves to the PRECEDING business day (Good Friday week
expires Thursday); a Mon-Thu weekly on a holiday moves to the FOLLOWING
business day (MLK-Monday weekly expires Tuesday). Collisions dedupe, which is
why Thanksgiving week has no Thursday expiry (it merges into Friday).
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

import exchange_calendars as xcals
import polars as pl
from pydantic import BaseModel, ConfigDict

from options_strategy.data.schemas import EXPIRIES_SCHEMA, SESSIONS_SCHEMA, validate_schema

ET = "America/New_York"


class ExpiryRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    friday_weeklies_from: dt.date = dt.date(2010, 1, 1)
    monday_weeklies_from: dt.date = dt.date(2016, 8, 15)
    wednesday_weeklies_from: dt.date = dt.date(2016, 2, 23)
    tue_thu_weeklies_from: dt.date = dt.date(2022, 5, 1)
    # PM-settled SPXW also listed on monthly (3rd) Fridays from here on:
    pm_weekly_on_monthly_friday_from: dt.date = dt.date(2016, 1, 1)
    max_weekly_horizon_days: int = 95
    max_monthly_horizon_days: int = 370


@lru_cache(maxsize=8)
def _xnys_cached(start_iso: str, end_iso: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS", start=start_iso, end=end_iso)


def _xnys(start: dt.date, end: dt.date) -> xcals.ExchangeCalendar:
    pad_start = (start - dt.timedelta(days=10)).isoformat()
    pad_end = (end + dt.timedelta(days=10)).isoformat()
    return _xnys_cached(pad_start, pad_end)


def load_sessions(start: dt.date, end: dt.date) -> pl.DataFrame:
    """Sessions with tz-aware ET open/close and early-close flag."""
    cal = _xnys(start, end)
    rows = []
    for s in cal.sessions_in_range(start.isoformat(), end.isoformat()):
        open_et = cal.session_open(s).tz_convert(ET)
        close_et = cal.session_close(s).tz_convert(ET)
        rows.append(
            {
                "session": s.date(),
                "open_et": open_et.to_pydatetime(),
                "close_et": close_et.to_pydatetime(),
                "early_close": close_et.time() < dt.time(16, 0),
            }
        )
    df = pl.DataFrame(rows, schema=SESSIONS_SCHEMA, orient="row")
    return validate_schema(df, SESSIONS_SCHEMA, "sessions")


def session_dates(start: dt.date, end: dt.date) -> set[dt.date]:
    cal = _xnys(start, end)
    return {s.date() for s in cal.sessions_in_range(start.isoformat(), end.isoformat())}


def third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    first_friday = first + dt.timedelta(days=(4 - first.weekday()) % 7)
    return first_friday + dt.timedelta(days=14)


def _previous_session(d: dt.date, sessions: set[dt.date]) -> dt.date:
    while d not in sessions:
        d -= dt.timedelta(days=1)
    return d


def _next_session(d: dt.date, sessions: set[dt.date]) -> dt.date:
    while d not in sessions:
        d += dt.timedelta(days=1)
    return d


def build_expiry_table(start: dt.date, end: dt.date, rules: ExpiryRules) -> pl.DataFrame:
    """Listed expiries in [start, end + horizons], holiday-shifted to sessions.

    SPX monthlies are AM-settled third Fridays; SPXW weeklies are PM-settled.
    A weekday only lists in its era. Holiday shift: Friday expiries move to the
    preceding session, Mon-Thu weeklies to the following session (CBOE
    convention; see module docstring).
    """
    horizon_end = end + dt.timedelta(days=rules.max_monthly_horizon_days)
    sessions = session_dates(start - dt.timedelta(days=8), horizon_end + dt.timedelta(days=8))

    monthly_dates: set[dt.date] = set()
    ym = (start.year, start.month)
    while dt.date(ym[0], ym[1], 1) <= horizon_end:
        tf = third_friday(*ym)
        if start <= tf <= horizon_end:
            shifted = _previous_session(tf, sessions)
            if shifted >= start:
                monthly_dates.add(shifted)
        ym = (ym[0] + 1, 1) if ym[1] == 12 else (ym[0], ym[1] + 1)

    weekly_horizon_end = end + dt.timedelta(days=rules.max_weekly_horizon_days)
    weekly_dates: set[dt.date] = set()
    d = start
    while d <= weekly_horizon_end:
        wd = d.weekday()
        eligible = (
            (wd == 4 and d >= rules.friday_weeklies_from)
            or (wd == 0 and d >= rules.monday_weeklies_from)
            or (wd == 2 and d >= rules.wednesday_weeklies_from)
            or (wd in (1, 3) and d >= rules.tue_thu_weeklies_from)
        )
        if eligible:
            if d in sessions:
                shifted = d
            elif wd == 4:
                shifted = _previous_session(d, sessions)
            else:
                shifted = _next_session(d, sessions)
            is_monthly_slot = shifted in monthly_dates
            keep = not is_monthly_slot or d >= rules.pm_weekly_on_monthly_friday_from
            if keep and shifted >= start:
                weekly_dates.add(shifted)
        d += dt.timedelta(days=1)

    rows = [
        {"expiry_date": e, "root": "SPX", "settlement": "AM"} for e in sorted(monthly_dates)
    ] + [{"expiry_date": e, "root": "SPXW", "settlement": "PM"} for e in sorted(weekly_dates)]
    df = pl.DataFrame(rows, schema=EXPIRIES_SCHEMA, orient="row").sort(["expiry_date", "root"])
    return validate_schema(df, EXPIRIES_SCHEMA, "expiries")
