"""Offline tests for the at_time slice -> world packager (no vendor data)."""

from __future__ import annotations

import datetime as dt
import json

import polars as pl

from options_strategy.data.schemas import OPTION_QUOTES_SCHEMA
from options_strategy.data.vendors.theta_slice_world import (
    build_world,
    parity_spot,
    to_option_quotes,
)

ENTRY = dt.date(2017, 1, 6)
FRONT = dt.date(2017, 1, 13)


def _raw_slice() -> pl.DataFrame:
    """Two snapshots x 10 parity-consistent strikes (df=1, F=5000: C-P=5000-K)."""
    rows = []
    for snap in ("10:00:00", "15:45:00"):
        for root, exp in (("SPXW", FRONT), ("SPX", dt.date(2017, 1, 20))):
            for k in range(4960, 5060, 10):
                put_mid = 60.0
                call_mid = 5060.0 - k
                for right, mid in (("call", call_mid), ("put", put_mid)):
                    rows.append(
                        {
                            "symbol": root,
                            "expiration": exp,
                            "strike": float(k),
                            "right": right,
                            "bid": mid - 0.5,
                            "ask": mid + 0.5,
                            "bid_size": 10,
                            "ask_size": 10,
                            "root": root,
                            "entry_date": ENTRY,
                            "snapshot_et": snap,
                            "regime_window": "calm-2017",
                            "ema_state": "bull",
                        }
                    )
    return pl.DataFrame(rows)


def test_to_option_quotes_schema_and_snapshots() -> None:
    q = to_option_quotes(_raw_slice())
    assert q.schema == pl.Schema(OPTION_QUOTES_SCHEMA)
    ts = q["ts"].unique().sort().to_list()
    assert [t.hour * 100 + t.minute for t in ts] == [1000, 1545]
    assert all(t.date() == ENTRY for t in ts)
    settle = dict(zip(q["root"].to_list(), q["am_pm_settle"].to_list(), strict=True))
    assert settle == {"SPX": "AM", "SPXW": "PM"}
    assert set(q["cp"].unique().to_list()) == {"C", "P"}


def test_parity_spot_recovers_constructed_forward() -> None:
    q = to_option_quotes(_raw_slice())
    ts = q["ts"].unique().sort().to_list()[0]
    spot = parity_spot(q, ts)
    assert spot is not None
    assert abs(spot - 5000.0) < 1.0  # df=1, F=5000 by construction


def test_build_world_layout_and_manifest(tmp_path) -> None:
    root = tmp_path / "slice"
    (root / "quotes").mkdir(parents=True)
    _raw_slice().write_parquet(root / "quotes" / f"{ENTRY}.parquet")
    manifest = build_world(root, data_version="theta_slice_vTEST")
    world = root / "world"
    assert manifest["data_version"] == "theta_slice_vTEST"
    assert manifest["n_sessions"] == 1
    assert manifest["snapshots_without_parity_spot"] == []
    quotes = pl.read_parquet(world / "option_quotes" / f"date={ENTRY}.parquet")
    assert quotes.schema == pl.Schema(OPTION_QUOTES_SCHEMA)
    bars = pl.read_parquet(world / "underlying_bars.parquet")
    assert bars.height == 2  # one parity-spot bar per snapshot
    assert bars["ts"].to_list() == quotes["ts"].unique().sort().to_list()
    sessions = pl.read_parquet(world / "sessions.parquet")
    assert sessions["session"].to_list() == [ENTRY]
    assert json.loads((world / "manifest.json").read_text())["n_quote_rows"] == quotes.height
