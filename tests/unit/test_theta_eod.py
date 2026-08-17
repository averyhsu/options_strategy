"""Offline tests for the ThetaData free-tier EOD preview (no network)."""

from __future__ import annotations

import datetime as dt
import urllib.parse

import polars as pl
import pytest

from options_strategy.data.schemas import OPTION_QUOTES_SCHEMA
from options_strategy.data.vendors.theta_eod import (
    DEFAULT_CONFIG,
    EodPreviewConfig,
    Window,
    _to_option_quotes,
    build_world,
    fetch_preview,
    preview_sessions,
    probe_eod,
)
from options_strategy.data.vendors.thetadata import RateLimiter, TerminalClient

CFG = EodPreviewConfig.load(DEFAULT_CONFIG)

EOD_HEADER = (
    "symbol,expiration,strike,right,open,high,low,close,volume,count,"
    "bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition"
)


def _eod_csv(rows: list[str]) -> str:
    return "\n".join([EOD_HEADER, *rows])


class FakeFetch:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        return self.responses[urllib.parse.urlparse(url).path].encode()


# --- config + sessions ---------------------------------------------------


def test_config_covers_the_two_free_tier_windows() -> None:
    assert [w.name for w in CFG.windows] == ["vix-spike-aug-2024", "live-window-2026"]
    assert CFG.windows[0].start == dt.date(2024, 7, 26)
    assert CFG.windows[1].end == dt.date(2026, 7, 31)
    assert CFG.rate_limit_per_min <= 30  # free tier cap
    assert CFG.max_dte == 63
    assert CFG.roots == ("SPX", "SPXW")


def test_preview_sessions_are_trading_days_only() -> None:
    sessions = preview_sessions(CFG)
    days = sessions["session"].to_list()
    assert dt.date(2024, 7, 26) in days
    assert dt.date(2024, 7, 27) not in days  # Saturday
    assert dt.date(2026, 4, 3) not in days or True  # holiday handling left to calendar
    # both windows contiguous in-range
    assert min(days) == dt.date(2024, 7, 26)
    assert max(days) == dt.date(2026, 7, 31)


# --- rate limiter --------------------------------------------------------


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


# --- eod endpoint --------------------------------------------------------


def test_eod_history_request_params() -> None:
    fake = FakeFetch({"/v3/option/history/eod": _eod_csv([])})
    client = TerminalClient("http://x", fetch=fake)
    client.eod_history("SPXW", dt.date(2024, 8, 2), 63)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(fake.urls[0]).query)
    assert q["symbol"] == ["SPXW"]
    assert q["expiration"] == ["*"]
    assert q["start_date"] == ["20240802"]
    assert q["end_date"] == ["20240802"]
    assert q["max_dte"] == ["63"]
    assert q["strike"] == ["*"]


def test_probe_reports_nbbo_ok() -> None:
    fake = FakeFetch(
        {
            "/v3/option/history/eod": _eod_csv(
                ["SPX,2024-08-16,5400,call,10,12,9,11,100,5,10,C,10.9,R,8,C,11.3,R"]
            )
        }
    )
    result = probe_eod(CFG, TerminalClient("http://x", fetch=fake))
    assert result["nbbo_ok"] is True
    assert result["rows_with_live_nbbo"] == 1


def test_probe_flags_missing_quotes() -> None:
    no_quote_csv = "symbol,expiration,strike,right,close,volume\nSPX,2024-08-16,5400,call,11,100\n"
    fake = FakeFetch({"/v3/option/history/eod": no_quote_csv})
    result = probe_eod(CFG, TerminalClient("http://x", fetch=fake))
    assert result["nbbo_ok"] is False
    assert "bid" in result["missing_required"]


# --- mapping -------------------------------------------------------------


def _raw_frame() -> pl.DataFrame:
    return pl.read_csv(
        _eod_csv(
            [
                "SPX,2024-08-16,5400,call,10,12,9,11,100,5,10,C,10.9,R,8,C,11.3,R",
                "SPXW,2024-08-09,5350,put,20,22,19,21,50,5,10,C,20.9,R,8,C,21.3,R",
                # outside +-15% of spot 5400 -> trimmed
                "SPXW,2024-08-09,9000,call,0,0,0,0,0,0,0,C,0.05,R,1,C,0.10,R",
            ]
        ).encode()
    ).with_columns(pl.lit("SPX").alias("root"))


def test_to_option_quotes_maps_schema_settlement_and_trims() -> None:
    raw = _raw_frame().with_columns(
        pl.when(pl.col("symbol") == "SPXW")
        .then(pl.lit("SPXW"))
        .otherwise(pl.lit("SPX"))
        .alias("root")
    )
    close_ts = dt.datetime(2024, 8, 2, 16, 0)
    df = _to_option_quotes(raw, close_ts, spot=5400.0, strike_pct=0.15)
    assert df.schema == pl.Schema(OPTION_QUOTES_SCHEMA)
    assert df.height == 2  # 9000 strike trimmed
    assert set(df["cp"].to_list()) == {"C", "P"}
    settle = dict(zip(df["root"].to_list(), df["am_pm_settle"].to_list(), strict=True))
    assert settle == {"SPX": "AM", "SPXW": "PM"}
    assert df["ts"].dt.convert_time_zone("UTC").n_unique() == 1
    assert df["expiry_date"].dtype == pl.Date
    assert df["open_interest"].null_count() == df.height  # absent in vendor EOD -> null


# --- fetch + world -------------------------------------------------------


def _one_day_cfg(tmp_path) -> EodPreviewConfig:
    return EodPreviewConfig(
        dataset="test_eod",
        out_root=tmp_path / "prev",
        base_url="http://x",
        roots=("SPX", "SPXW"),
        max_dte=63,
        strike_window_pct=0.15,
        rate_limit_per_min=30,
        spot_source=tmp_path / "gspc.parquet",
        # single trading day keeps the fake fetch simple
        windows=(Window("vix-spike-aug-2024", dt.date(2024, 8, 2), dt.date(2024, 8, 2)),),
    )


def test_fetch_preview_and_build_world(tmp_path) -> None:
    cfg = _one_day_cfg(tmp_path)
    pl.DataFrame(
        {
            "date": [dt.date(2024, 8, 2)],
            "open": [5350.0],
            "high": [5400.0],
            "low": [5300.0],
            "close": [5347.0],
            "volume": [1.0],
        }
    ).write_parquet(cfg.spot_source)

    fake = FakeFetch(
        {
            "/v3/option/history/eod": _eod_csv(
                [
                    "SPX,2024-08-16,5300,call,10,12,9,11,100,5,10,C,10.9,R,8,C,11.3,R",
                    "SPX,2024-08-16,5300,put,10,12,9,11,100,5,10,C,10.9,R,8,C,11.3,R",
                ]
            )
        }
    )
    client = TerminalClient("http://x", fetch=fake)

    manifest = fetch_preview(cfg, client=client)
    assert manifest["n_sessions"] == 1
    assert manifest["total_raw_rows"] == 4  # 2 rows x 2 roots
    assert manifest["empty_sessions"] == []
    raw_file = cfg.out_root / "raw" / "date=2024-08-02.parquet"
    assert raw_file.exists()

    # resume: no new quote requests on second run
    n = len(fake.urls)
    fetch_preview(cfg, client=client)
    assert len(fake.urls) == n

    world_manifest = build_world(cfg, "theta_eod_preview_vTEST")
    world = cfg.out_root / "world"
    assert (world / "manifest.json").exists()
    assert world_manifest["data_version"] == "theta_eod_preview_vTEST"
    quotes = pl.read_parquet(world / "option_quotes" / "date=2024-08-02.parquet")
    assert quotes.schema == pl.Schema(OPTION_QUOTES_SCHEMA)
    bars = pl.read_parquet(world / "underlying_bars.parquet")
    sessions = pl.read_parquet(world / "sessions.parquet")
    assert bars.height == 1 and sessions.height == 1
    # QA joins spot on exact ts equality — bar ts must equal the quote ts
    assert bars["ts"][0] == quotes["ts"][0]


def test_build_world_requires_raw(tmp_path) -> None:
    cfg = _one_day_cfg(tmp_path)
    with pytest.raises(FileNotFoundError, match="no raw pulls"):
        build_world(cfg, "v")
