"""Offline tests for the ThetaData acquisition module (no network, no vendor data).

The fake below mimics the official ``thetadata.ThetaClient`` surface the
adapter uses (three methods, polars frames, NoDataFoundError on empties).
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from options_strategy.data.vendors.thetadata import (
    DEFAULT_CONFIG,
    RateLimiter,
    SliceConfig,
    ThetaSession,
    VendorError,
    ensure_expiration_date,
    expiries_in_scope,
    fetch_sample_date,
    fetch_slice,
)

CFG = SliceConfig.load(DEFAULT_CONFIG)


class NoDataFoundError(Exception):
    """Same class NAME as the vendor library's empty-result error."""


def quote_frame(rows: list[dict]) -> pl.DataFrame:
    schema = {
        "symbol": pl.Utf8,
        "expiration": pl.Utf8,
        "strike": pl.Float64,
        "right": pl.Utf8,
        "timestamp": pl.Utf8,
        "bid_size": pl.Int64,
        "bid_exchange": pl.Utf8,
        "bid": pl.Float64,
        "bid_condition": pl.Utf8,
        "ask_size": pl.Int64,
        "ask_exchange": pl.Utf8,
        "ask": pl.Float64,
        "ask_condition": pl.Utf8,
    }
    return pl.DataFrame(rows, schema=schema)


def qrow(exp: str, strike: float, right: str, bid: float, ask: float) -> dict:
    return {
        "symbol": "SPXW",
        "expiration": exp,
        "strike": strike,
        "right": right,
        "timestamp": "2017-01-06T15:45:00",
        "bid_size": 10,
        "bid_exchange": "C",
        "bid": bid,
        "bid_condition": "R",
        "ask_size": 8,
        "ask_exchange": "C",
        "ask": ask,
        "ask_condition": "R",
    }


class FakeLib:
    """Records every call; serves canned frames keyed by method name."""

    options_subscription = "STANDARD"
    stock_subscription = "FREE"
    index_subscription = None

    def __init__(self, responses: dict[str, pl.DataFrame | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def _serve(self, method: str, kw: dict):
        self.calls.append((method, kw))
        resp = self.responses[method]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def option_list_expirations(self, **kw):
        return self._serve("option_list_expirations", kw)

    def option_at_time_quote(self, **kw):
        return self._serve("option_at_time_quote", kw)

    def option_history_eod(self, **kw):
        return self._serve("option_history_eod", kw)


def session_of(fake: FakeLib) -> ThetaSession:
    return ThetaSession(fake, sleeper=lambda _s: None)


# --- spec config ---------------------------------------------------------


def test_spec_has_51_sample_dates_matching_report_windows() -> None:
    assert len(CFG.samples) == 51
    by_window: dict[str, int] = {}
    for s in CFG.samples:
        by_window[s.window] = by_window.get(s.window, 0) + 1
    assert by_window == {
        "calm-2017": 6,
        "volmageddon-feb-2018": 5,
        "covid-mar-2020": 7,
        "bear-2022": 10,
        "vix-spike-aug-2024": 5,
        "live-window-2026": 18,
    }


def test_spec_rows_are_sane() -> None:
    dates = [s.entry_date for s in CFG.samples]
    assert dates == sorted(dates)
    assert len(set(dates)) == 51
    assert dates[0] == dt.date(2017, 1, 6)
    assert dates[-1] == dt.date(2026, 7, 31)
    for s in CFG.samples:
        # entry dates are Fridays except holiday-shifted Thursdays
        assert s.entry_date.weekday() in (3, 4)
        # strike window brackets spot at roughly ±4%
        assert s.strike_lo < s.spot < s.strike_hi
        assert 0.03 < (s.spot - s.strike_lo) / s.spot < 0.06
        assert 0.03 < (s.strike_hi - s.spot) / s.spot < 0.06
    assert CFG.roots == ("SPX", "SPXW")
    assert CFG.max_dte == 63
    assert CFG.primary_snapshot in CFG.snapshot_times
    assert CFG.creds_file.name == "creds.txt"


def test_all_sample_dates_within_standard_tier_history() -> None:
    # Options STANDARD history starts 2016-01-01; every sample date must be after.
    for s in CFG.samples:
        assert s.entry_date >= dt.date(2016, 1, 1)


# --- DTE scoping ---------------------------------------------------------


def test_expiries_in_scope_calendar_dte_bounds() -> None:
    d = dt.date(2020, 3, 6)
    exps = [
        dt.date(2020, 3, 6),  # 0 DTE: excluded (front week is the NEXT Friday)
        dt.date(2020, 3, 13),  # 7
        dt.date(2020, 5, 8),  # 63: included
        dt.date(2020, 5, 15),  # 70: excluded
    ]
    assert expiries_in_scope(exps, d, 63) == [dt.date(2020, 3, 13), dt.date(2020, 5, 8)]


# --- session wrapper -----------------------------------------------------


def test_at_time_quote_call_arguments() -> None:
    frame = quote_frame([qrow("2017-01-13", 2270, "call", 12.5, 13.1)])
    fake = FakeLib({"option_at_time_quote": frame})
    df = session_of(fake).at_time_quote(
        "SPXW", dt.date(2017, 1, 13), dt.date(2017, 1, 6), "15:45:00"
    )
    assert df.height == 1
    method, kw = fake.calls[0]
    assert method == "option_at_time_quote"
    assert kw == {
        "symbol": "SPXW",
        "start_date": dt.date(2017, 1, 6),
        "end_date": dt.date(2017, 1, 6),
        "time_of_day": "15:45:00",
        "expiration": dt.date(2017, 1, 13),
        "strike": "*",
        "right": "both",
    }


def test_no_data_error_is_empty_frame_not_error() -> None:
    fake = FakeLib({"option_at_time_quote": NoDataFoundError("no data")})
    df = session_of(fake).at_time_quote(
        "SPX", dt.date(2020, 3, 13), dt.date(2020, 3, 6), "10:00:00"
    )
    assert df.is_empty()


def test_transient_errors_retry_then_raise() -> None:
    fake = FakeLib({"option_list_expirations": RuntimeError("grpc unavailable")})
    with pytest.raises(VendorError, match="failed after 3 tries"):
        session_of(fake).list_expirations("SPXW")
    assert len(fake.calls) == 3


def test_list_expirations_parses_sorts_dedupes() -> None:
    fake = FakeLib(
        {
            "option_list_expirations": pl.DataFrame(
                {"symbol": ["SPXW"] * 3, "expiration": ["2017-01-20", "2017-01-13", "2017-01-20"]}
            )
        }
    )
    assert session_of(fake).list_expirations("SPXW") == [dt.date(2017, 1, 13), dt.date(2017, 1, 20)]


def test_ensure_expiration_date_handles_str_and_date() -> None:
    as_str = pl.DataFrame({"expiration": ["2017-01-13", "20170120"]})
    out = ensure_expiration_date(as_str)
    assert out["expiration"].to_list() == [dt.date(2017, 1, 13), dt.date(2017, 1, 20)]
    as_date = pl.DataFrame({"expiration": [dt.date(2017, 1, 13)]})
    assert ensure_expiration_date(as_date)["expiration"].dtype == pl.Date


def test_rate_limiter_spaces_requests() -> None:
    t = {"now": 0.0}
    sleeps: list[float] = []

    def clock() -> float:
        return t["now"]

    def sleeper(s: float) -> None:
        sleeps.append(s)
        t["now"] += s

    rl = RateLimiter(30, clock=clock, sleeper=sleeper)
    rl.wait()  # first call free
    rl.wait()  # must wait the full 2s interval
    t["now"] += 1.5
    rl.wait()  # only 0.5s remaining
    assert sleeps == [2.0, 0.5]


# --- fetch + persist -----------------------------------------------------


def _mini_cfg(out_root) -> SliceConfig:
    return SliceConfig(
        dataset="test_slice",
        out_root=out_root,
        creds_file=CFG.creds_file,
        roots=("SPXW",),
        max_dte=63,
        snapshot_times=("15:45:00",),
        primary_snapshot="15:45:00",
        strike_pad_points=50.0,
        rate_limit_per_min=28,
        samples=(CFG.samples[0],),  # 2017-01-06, strikes 2185-2370
    )


def _mini_fake() -> FakeLib:
    return FakeLib(
        {
            "option_list_expirations": pl.DataFrame(
                {"symbol": ["SPXW", "SPXW"], "expiration": ["2017-01-13", "2017-06-30"]}
            ),
            "option_at_time_quote": quote_frame(
                [
                    qrow("2017-01-13", 2270, "call", 12.5, 13.1),  # inside window
                    qrow("2017-01-13", 2270, "put", 11.0, 11.6),
                    qrow("2017-01-13", 2150, "put", 1.0, 1.3),  # within the 50-pt pad
                    qrow("2017-01-13", 1500, "put", 0.1, 0.2),  # far outside: dropped
                ]
            ),
        }
    )


def test_fetch_sample_date_filters_and_annotates() -> None:
    fake = _mini_fake()
    session = session_of(fake)
    cfg = _mini_cfg(None)
    df = fetch_sample_date(session, cfg, cfg.samples[0])
    # 1500-strike row is outside window+pad and filtered out
    assert df["strike"].to_list() == [2150.0, 2270.0, 2270.0]
    assert set(df["root"].to_list()) == {"SPXW"}
    assert df["entry_date"].unique().to_list() == [dt.date(2017, 1, 6)]
    assert df["expiration"].dtype == pl.Date
    assert df["regime_window"].unique().to_list() == ["calm-2017"]
    quote_calls = [c for c in fake.calls if c[0] == "option_at_time_quote"]
    assert len(quote_calls) == 1  # 1 root x 1 snapshot, BULK expiration=*
    assert quote_calls[0][1]["expiration"] == "*"
    assert quote_calls[0][1]["max_dte"] == 63


def test_fetch_slice_writes_parquet_manifest_and_resumes(tmp_path) -> None:
    import json

    cfg = _mini_cfg(tmp_path / "slice")
    fake = _mini_fake()
    session = session_of(fake)
    manifest = fetch_slice(cfg, session=session)
    out = cfg.out_root / "quotes" / "2017-01-06.parquet"
    assert out.exists()
    assert manifest["total_rows"] == 3
    assert manifest["n_dates_with_data"] == 1
    assert manifest["empty_dates"] == []
    stats = manifest["per_date"][0]
    assert stats["crossed_quotes"] == 0
    assert stats["zero_bids"] == 0
    on_disk = json.loads((cfg.out_root / "manifest.json").read_text())
    assert on_disk["total_rows"] == 3
    # resume: second run must not refetch quotes for the existing date
    n_quote_calls = len([c for c in fake.calls if c[0] == "option_at_time_quote"])
    fetch_slice(cfg, session=session)
    assert len([c for c in fake.calls if c[0] == "option_at_time_quote"]) == n_quote_calls


def test_missing_columns_raise() -> None:
    fake = FakeLib({"option_at_time_quote": pl.DataFrame({"symbol": ["SPXW"], "strike": [2270.0]})})
    session = session_of(fake)
    cfg = _mini_cfg(None)
    with pytest.raises(VendorError, match="missing columns"):
        fetch_sample_date(session, cfg, cfg.samples[0])
