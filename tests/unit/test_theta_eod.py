"""Offline tests for the ThetaData free-tier EOD preview (no network)."""

from __future__ import annotations

import datetime as dt

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
from options_strategy.data.vendors.thetadata import ThetaSession

CFG = EodPreviewConfig.load(DEFAULT_CONFIG)

EOD_COLS = [
    "symbol", "expiration", "strike", "right", "open", "high", "low", "close",
    "volume", "count", "bid_size", "bid_exchange", "bid", "bid_condition",
    "ask_size", "ask_exchange", "ask", "ask_condition",
]


def eod_frame(rows: list[list]) -> pl.DataFrame:
    return pl.DataFrame([dict(zip(EOD_COLS, r, strict=True)) for r in rows])


ROW_CALL = ["SPX", "2024-08-16", 5400.0, "call", 10.0, 12.0, 9.0, 11.0, 100, 5,
            10, "C", 10.9, "R", 8, "C", 11.3, "R"]
ROW_PUT = ["SPXW", "2024-08-09", 5350.0, "put", 20.0, 22.0, 19.0, 21.0, 50, 5,
           10, "C", 20.9, "R", 8, "C", 21.3, "R"]
ROW_FAR = ["SPXW", "2024-08-09", 9000.0, "call", 0.0, 0.0, 0.0, 0.0, 0, 0,
           0, "C", 0.05, "R", 1, "C", 0.10, "R"]


class FakeLib:
    options_subscription = "FREE"
    stock_subscription = "FREE"
    index_subscription = None

    def __init__(self, eod: pl.DataFrame) -> None:
        self.eod = eod
        self.calls: list[dict] = []

    def option_history_eod(self, **kw):
        self.calls.append(kw)
        return self.eod


def session_of(fake: FakeLib) -> ThetaSession:
    return ThetaSession(fake, sleeper=lambda _s: None)


# --- config + sessions ---------------------------------------------------


def test_config_covers_the_two_free_tier_windows() -> None:
    assert [w.name for w in CFG.windows] == ["vix-spike-aug-2024", "live-window-2026"]
    assert CFG.windows[0].start == dt.date(2024, 7, 26)
    assert CFG.windows[1].end == dt.date(2026, 7, 31)
    assert CFG.rate_limit_per_min <= 30  # free tier cap
    assert CFG.max_dte == 63
    assert CFG.roots == ("SPX", "SPXW")
    assert CFG.creds_file.name == "creds.txt"


def test_preview_sessions_are_trading_days_only() -> None:
    sessions = preview_sessions(CFG)
    days = sessions["session"].to_list()
    assert dt.date(2024, 7, 26) in days
    assert dt.date(2024, 7, 27) not in days  # Saturday
    assert min(days) == dt.date(2024, 7, 26)
    assert max(days) == dt.date(2026, 7, 31)


# --- eod request + probe -------------------------------------------------


def test_eod_history_call_arguments() -> None:
    fake = FakeLib(eod_frame([ROW_CALL]))
    session_of(fake).eod_history("SPXW", dt.date(2024, 8, 2), 63)
    assert fake.calls[0] == {
        "symbol": "SPXW",
        "start_date": dt.date(2024, 8, 2),
        "end_date": dt.date(2024, 8, 2),
        "expiration": "*",
        "strike": "*",
        "right": "both",
        "max_dte": 63,
    }


def test_probe_reports_nbbo_ok_and_subscriptions() -> None:
    result = probe_eod(CFG, session_of(FakeLib(eod_frame([ROW_CALL]))))
    assert result["nbbo_ok"] is True
    assert result["rows_with_live_nbbo"] == 1
    assert result["subscriptions"]["options"] == "FREE"


def test_probe_flags_missing_quotes() -> None:
    no_quotes = pl.DataFrame(
        {"symbol": ["SPX"], "expiration": ["2024-08-16"], "strike": [5400.0],
         "right": ["call"], "close": [11.0], "volume": [100]}
    )
    result = probe_eod(CFG, session_of(FakeLib(no_quotes)))
    assert result["nbbo_ok"] is False
    assert "bid" in result["missing_required"]


# --- mapping -------------------------------------------------------------


def test_to_option_quotes_maps_schema_settlement_and_trims() -> None:
    raw = eod_frame([ROW_CALL, ROW_PUT, ROW_FAR]).with_columns(
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


def test_to_option_quotes_accepts_date_typed_expiration() -> None:
    raw = eod_frame([ROW_CALL]).with_columns(
        pl.col("expiration").str.to_date("%Y-%m-%d"), pl.lit("SPX").alias("root")
    )
    df = _to_option_quotes(raw, dt.datetime(2024, 8, 2, 16, 0), spot=5400.0, strike_pct=0.15)
    assert df["expiry_date"].to_list() == [dt.date(2024, 8, 16)]


# --- fetch + world -------------------------------------------------------


def _one_day_cfg(out_root, tmp_path) -> EodPreviewConfig:
    return EodPreviewConfig(
        dataset="test_eod",
        out_root=out_root,
        creds_file=CFG.creds_file,
        roots=("SPX", "SPXW"),
        max_dte=63,
        strike_window_pct=0.15,
        rate_limit_per_min=30,
        spot_source=tmp_path / "gspc.parquet",
        # single trading day keeps the fake simple
        windows=(Window("vix-spike-aug-2024", dt.date(2024, 8, 2), dt.date(2024, 8, 2)),),
    )


def test_fetch_preview_and_build_world(tmp_path) -> None:
    cfg = _one_day_cfg(tmp_path / "prev", tmp_path)
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

    call2 = list(ROW_CALL)
    call2[3] = "put"
    fake = FakeLib(eod_frame([ROW_CALL, call2]))
    session = session_of(fake)

    manifest = fetch_preview(cfg, session=session)
    assert manifest["n_sessions"] == 1
    assert manifest["total_raw_rows"] == 4  # 2 rows x 2 roots
    assert manifest["empty_sessions"] == []
    raw_file = cfg.out_root / "raw" / "date=2024-08-02.parquet"
    assert raw_file.exists()

    # resume: no new eod requests on second run
    n = len(fake.calls)
    fetch_preview(cfg, session=session)
    assert len(fake.calls) == n

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
    cfg = _one_day_cfg(tmp_path / "prev", tmp_path)
    with pytest.raises(FileNotFoundError, match="no raw pulls"):
        build_world(cfg, "v")
