"""Offline tests for the ThetaData acquisition module (no network, no vendor data)."""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse

import polars as pl
import pytest

from options_strategy.data.vendors.thetadata import (
    DEFAULT_CONFIG,
    SliceConfig,
    TerminalClient,
    expiries_in_scope,
    fetch_sample_date,
    fetch_slice,
)

CFG = SliceConfig.load(DEFAULT_CONFIG)


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


def test_all_sample_dates_within_standard_tier_history() -> None:
    # Options STANDARD history starts 2016-01-01; every sample date must be after.
    for s in CFG.samples:
        assert s.entry_date >= dt.date(2016, 1, 1)


# --- DTE scoping ---------------------------------------------------------


def test_expiries_in_scope_calendar_dte_bounds() -> None:
    d = dt.date(2020, 3, 6)
    exps = [
        dt.date(2020, 3, 6),   # 0 DTE: excluded (front week is the NEXT Friday)
        dt.date(2020, 3, 13),  # 7
        dt.date(2020, 5, 8),   # 63: included
        dt.date(2020, 5, 15),  # 70: excluded
    ]
    assert expiries_in_scope(exps, d, 63) == [dt.date(2020, 3, 13), dt.date(2020, 5, 8)]


# --- client --------------------------------------------------------------


class FakeFetch:
    """Records URLs; serves canned CSV per path."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        parsed = urllib.parse.urlparse(url)
        return self.responses[parsed.path].encode()


QUOTE_HEADER = (
    "symbol,expiration,strike,right,timestamp,bid_size,bid_exchange,bid,"
    "bid_condition,ask_size,ask_exchange,ask,ask_condition"
)


def _quote_csv(rows: list[str]) -> str:
    return "\n".join([QUOTE_HEADER, *rows])


def test_at_time_quote_request_and_parse() -> None:
    fake = FakeFetch(
        {
            "/v3/option/at_time/quote": _quote_csv(
                ["SPXW,2017-01-13,2270,call,2017-01-06T15:45:00,10,C,12.5,R,8,C,13.1,R"]
            )
        }
    )
    client = TerminalClient("http://127.0.0.1:25503", fetch=fake)
    df = client.at_time_quote("SPXW", dt.date(2017, 1, 13), dt.date(2017, 1, 6), "15:45:00")
    assert df.height == 1
    q = urllib.parse.parse_qs(urllib.parse.urlparse(fake.urls[0]).query)
    assert q["symbol"] == ["SPXW"]
    assert q["expiration"] == ["20170113"]
    assert q["start_date"] == ["20170106"]
    assert q["end_date"] == ["20170106"]
    assert q["time_of_day"] == ["15:45:00.000"]
    assert q["strike"] == ["*"]
    assert q["right"] == ["both"]
    assert q["format"] == ["csv"]


def test_empty_body_is_empty_frame_not_error() -> None:
    fake = FakeFetch({"/v3/option/at_time/quote": ""})
    client = TerminalClient("http://x", fetch=fake)
    df = client.at_time_quote("SPX", dt.date(2020, 3, 13), dt.date(2020, 3, 6), "10:00:00")
    assert df.is_empty()


def test_list_expirations_parses_and_sorts() -> None:
    fake = FakeFetch(
        {"/v3/option/list/expirations": "symbol,expiration\nSPXW,2017-01-20\nSPXW,2017-01-13\n"}
    )
    client = TerminalClient("http://x", fetch=fake)
    assert client.list_expirations("SPXW") == [dt.date(2017, 1, 13), dt.date(2017, 1, 20)]


# --- fetch + persist -----------------------------------------------------


def _mini_cfg(out_root) -> SliceConfig:
    return SliceConfig(
        dataset="test_slice",
        out_root=out_root,
        base_url="http://x",
        roots=("SPXW",),
        max_dte=63,
        snapshot_times=("15:45:00",),
        primary_snapshot="15:45:00",
        strike_pad_points=50.0,
        samples=(CFG.samples[0],),  # 2017-01-06, strikes 2185-2370
    )


def _mini_client() -> tuple[TerminalClient, FakeFetch]:
    fake = FakeFetch(
        {
            "/v3/option/list/expirations": "symbol,expiration\nSPXW,2017-01-13\nSPXW,2017-06-30\n",
            "/v3/option/at_time/quote": _quote_csv(
                [
                    # inside window
                    "SPXW,2017-01-13,2270,call,2017-01-06T15:45:00,10,C,12.5,R,8,C,13.1,R",
                    "SPXW,2017-01-13,2270,put,2017-01-06T15:45:00,10,C,11.0,R,8,C,11.6,R",
                    # within the 50-pt pad below strike_lo=2185
                    "SPXW,2017-01-13,2150,put,2017-01-06T15:45:00,5,C,1.0,R,5,C,1.3,R",
                    # far outside window + pad: dropped
                    "SPXW,2017-01-13,1500,put,2017-01-06T15:45:00,5,C,0.1,R,5,C,0.2,R",
                ]
            ),
        }
    )
    return TerminalClient("http://x", fetch=fake), fake


def test_fetch_sample_date_filters_and_annotates() -> None:
    client, fake = _mini_client()
    cfg = _mini_cfg(None)
    exps = {"SPXW": client.list_expirations("SPXW")}
    df = fetch_sample_date(client, cfg, cfg.samples[0], exps)
    # only the 2017-01-13 expiry is <= 63 DTE; 1500-strike row filtered out
    assert df["strike"].to_list() == [2150.0, 2270.0, 2270.0]
    assert set(df["root"].to_list()) == {"SPXW"}
    assert df["entry_date"].unique().to_list() == [dt.date(2017, 1, 6)]
    assert df["expiration"].dtype == pl.Date
    assert df["regime_window"].unique().to_list() == ["calm-2017"]
    # one quote request (1 root x 1 expiry in scope x 1 snapshot) + 1 listing
    quote_calls = [u for u in fake.urls if "at_time" in u]
    assert len(quote_calls) == 1


def test_fetch_slice_writes_parquet_manifest_and_resumes(tmp_path) -> None:
    cfg = _mini_cfg(tmp_path / "slice")
    client, fake = _mini_client()
    manifest = fetch_slice(cfg, client=client)
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
    n_quote_calls = len([u for u in fake.urls if "at_time" in u])
    fetch_slice(cfg, client=client)
    assert len([u for u in fake.urls if "at_time" in u]) == n_quote_calls


def test_missing_columns_raise() -> None:
    fake = FakeFetch(
        {
            "/v3/option/list/expirations": "symbol,expiration\nSPXW,2017-01-13\n",
            "/v3/option/at_time/quote": "symbol,strike\nSPXW,2270\n",
        }
    )
    client = TerminalClient("http://x", fetch=fake)
    cfg = _mini_cfg(None)
    with pytest.raises(Exception, match="missing columns"):
        fetch_sample_date(client, cfg, cfg.samples[0], {"SPXW": [dt.date(2017, 1, 13)]})
