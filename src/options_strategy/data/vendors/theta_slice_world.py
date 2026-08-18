"""Package the 51-date at_time slice into the standard world layout for QA.

Input: data/raw/thetadata/credit_check_slice/quotes/<entry_date>.parquet
(raw vendor at_time rows for 3 ET snapshots), from vendors/thetadata.py.

Output world (same root, world/): option_quotes/date=*.parquet in
OPTION_QUOTES_SCHEMA (ts = entry_date + snapshot time, ET), sessions,
underlying_bars, manifest.json.

Underlying bars are PARITY-DERIVED (no index subscription — plan amendment
2026-08-18): per (date, snapshot) the front SPXW expiry's put-call parity
fit gives forward and df; spot ~= forward x df (dividend carry ignored at
<= 9-day tenor: bias ~ div_yield x tau ~ <1 bp x week). OHLC collapse to
that single spot per bar.

Usage: python -m options_strategy.data.vendors.theta_slice_world \
           [--data-version theta_slice_v1]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from options_strategy.data.calendar import load_sessions
from options_strategy.data.schemas import OPTION_QUOTES_SCHEMA, validate_schema
from options_strategy.data.vendors.thetadata import VendorError
from options_strategy.pricing.forwards import fit_parity

ET = ZoneInfo("America/New_York")
SLICE_ROOT = Path("data/raw/thetadata/credit_check_slice")
MIN_PARITY_STRIKES = 8


def _snap_ts(date: dt.date, hms: str) -> dt.datetime:
    h, m, s = (int(x) for x in hms.split(":"))
    return dt.datetime(date.year, date.month, date.day, h, m, s, tzinfo=ET)


def to_option_quotes(raw: pl.DataFrame) -> pl.DataFrame:
    date = raw["entry_date"][0]
    out = (
        raw.with_columns(
            pl.col("snapshot_et")
            .map_elements(
                lambda t: _snap_ts(date, t),
                return_dtype=pl.Datetime("us", "America/New_York"),
            )
            .alias("ts")
        )
        .select(
            pl.col("ts"),
            pl.col("root").cast(pl.String),
            pl.col("expiration").alias("expiry_date"),
            pl.when(pl.col("root") == "SPX")
            .then(pl.lit("AM"))
            .otherwise(pl.lit("PM"))
            .alias("am_pm_settle"),
            pl.col("strike").cast(pl.Float64),
            pl.col("right").cast(pl.Utf8).str.to_uppercase().str.slice(0, 1).alias("cp"),
            pl.col("bid").cast(pl.Float64),
            pl.col("ask").cast(pl.Float64),
            pl.col("bid_size").cast(pl.Int64),
            pl.col("ask_size").cast(pl.Int64),
            pl.lit(None, dtype=pl.Float64).alias("last"),
            pl.lit(None, dtype=pl.Int64).alias("volume"),
            pl.lit(None, dtype=pl.Int64).alias("open_interest"),
            pl.lit(0, dtype=pl.Int32).alias("quote_condition"),
        )
        .sort(["ts", "root", "expiry_date", "strike", "cp"])
    )
    return validate_schema(out, OPTION_QUOTES_SCHEMA, "theta_slice option_quotes")


def parity_spot(quotes: pl.DataFrame, ts: dt.datetime) -> float | None:
    """Front-SPXW parity spot for one snapshot: forward_hat x df_hat."""
    snap = quotes.filter(
        (pl.col("ts") == ts)
        & (pl.col("root") == "SPXW")
        & (pl.col("bid") > 0)
        & (pl.col("ask") >= pl.col("bid"))
    )
    if snap.is_empty():
        return None
    front = snap["expiry_date"].min()
    mids = (
        snap.filter(pl.col("expiry_date") == front)
        .with_columns(((pl.col("bid") + pl.col("ask")) / 2).alias("mid"))
        .pivot(on="cp", index="strike", values="mid", aggregate_function="mean")
        .drop_nulls()
        .sort("strike")
    )
    if mids.height < MIN_PARITY_STRIKES or "C" not in mids.columns or "P" not in mids.columns:
        return None
    fit = fit_parity(mids["strike"].to_numpy(), mids["C"].to_numpy(), mids["P"].to_numpy())
    if not (np.isfinite(fit.forward) and fit.df > 0):
        return None
    return float(fit.forward * fit.df)


def build_world(slice_root: Path = SLICE_ROOT, data_version: str = "theta_slice_v1") -> dict:
    qfiles = sorted((slice_root / "quotes").glob("*.parquet"))
    if not qfiles:
        raise VendorError(f"no slice quote files under {slice_root / 'quotes'}")
    world = slice_root / "world"
    qdir = world / "option_quotes"
    qdir.mkdir(parents=True, exist_ok=True)

    dates: list[dt.date] = []
    bar_rows: list[dict] = []
    total = 0
    no_spot: list[str] = []
    for f in qfiles:
        raw = pl.read_parquet(f)
        quotes = to_option_quotes(raw)
        date = quotes["ts"][0].date()
        quotes.write_parquet(qdir / f"date={date}.parquet")
        dates.append(date)
        total += quotes.height
        for ts in quotes["ts"].unique().sort().to_list():
            spot = parity_spot(quotes, ts)
            if spot is None:
                no_spot.append(str(ts))
                continue
            bar_rows.append({"ts": ts, "open": spot, "high": spot, "low": spot, "close": spot})

    pl.DataFrame(bar_rows).sort("ts").write_parquet(world / "underlying_bars.parquet")
    sessions = load_sessions(min(dates), max(dates))
    sessions.filter(pl.col("session").is_in(dates)).write_parquet(world / "sessions.parquet")

    manifest = {
        "data_version": data_version,
        "vendor": "thetadata",
        "dataset": "credit_check_slice",
        "kind": "REAL vendor at_time slice (51 spec dates x 3 ET snapshots)",
        "built_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "underlying_note": (
            "underlying_bars = PARITY-DERIVED spot (front SPXW fit, forward x df; "
            "no index subscription per 2026-08-18 amendment)"
        ),
        "n_sessions": len(dates),
        "n_quote_rows": total,
        "snapshots_without_parity_spot": no_spot,
    }
    (world / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-version", default="theta_slice_v1")
    args = ap.parse_args()
    print(json.dumps(build_world(data_version=args.data_version), indent=2))


if __name__ == "__main__":
    main()
