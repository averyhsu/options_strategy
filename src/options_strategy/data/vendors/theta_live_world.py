"""Engine-grade REAL world from the bars15 decade store (Pass 2, step 6).

Window 2024-06-03 -> 2026-08-07: long enough that the percentile-band
family's trailing above-EMA history (min 52 completed weeks) accumulates
INSIDE the world before the fingerprint window (2026-04-01 -> 2026-07-30),
because the engine's daily-history prefix and the sessions table must cover
identical day lists.

World contract (all internal schemas; adapters read it unchanged):
    option_quotes/date=*.parquet   15-min NBBO snapshots, 27 bars/session
    underlying_bars.parquet        parity-derived spot per bar (front-SPXW
                                   fit x df; no index subscription)
    sessions / expiries / rates / settlements / manifest.json

Documented proxies (ASSUMPTIONS 2026-08-23): per-bar OHLC collapse to the
bar's parity spot (intra-bar extremes unavailable at 15-min NBBO cadence);
PM settlements = last-bar parity spot of expiry day, AM (SET) = first-bar
parity spot; rates = FRED DTB3 at a single 91d tenor.

Usage:  python -m options_strategy.data.vendors.theta_live_world
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy.data.calendar import load_sessions
from options_strategy.data.schemas import (
    EXPIRIES_SCHEMA,
    OPTION_QUOTES_SCHEMA,
    RATES_SCHEMA,
    SETTLEMENTS_SCHEMA,
    validate_schema,
)
from options_strategy.data.vendors.thetadata import VendorError
from options_strategy.pricing.forwards import fit_parity

BARS_DIR = Path("data/raw/theta/bars15/raw")
OUT_ROOT = Path("data/raw/theta/live_world")
DTB3 = Path("data/raw/free/dtb3_daily.parquet")
WINDOW_START = dt.date(2024, 6, 3)
WINDOW_END = dt.date(2026, 8, 7)
MIN_PARITY_STRIKES = 8


def to_quotes(raw: pl.DataFrame) -> pl.DataFrame:
    # the vendor feed carries occasional NaN bid/ask rows, and polars treats
    # NaN > 0 as TRUE — they'd sail through every "live quote" filter and
    # poison parity fits and marks. Drop them here (counted by the caller).
    raw = raw.filter(~(pl.col("bid").is_nan() | pl.col("ask").is_nan()))
    # drop the 16:00 closing-state bar: quote quality there is degraded (QA:
    # most bad parity fits sit at 16:00) and the spec's PRIMARY basis is
    # 15:45 — so the engine's "EOD = last bar" convention lands on 15:45.
    # Settlements are computed separately from the pre-drop parity spots.
    raw = raw.filter(pl.col("timestamp").dt.hour() < 16)
    out = raw.select(
        pl.col("timestamp").dt.cast_time_unit("us").alias("ts"),
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
    ).sort(["ts", "root", "expiry_date", "strike", "cp"])
    return validate_schema(out, OPTION_QUOTES_SCHEMA, "theta_live option_quotes")


def parity_spots_for_session(quotes: pl.DataFrame) -> pl.DataFrame:
    """One parity spot per snapshot ts: shortest SPXW expiry (>0 DTE) with
    >= MIN_PARITY_STRIKES double-live pairs; forward x df."""
    live = quotes.filter(
        (pl.col("root") == "SPXW")
        & pl.col("bid").is_not_nan()
        & pl.col("ask").is_not_nan()
        & (pl.col("bid") > 0)
        & (pl.col("ask") >= pl.col("bid"))
        & (pl.col("expiry_date") > pl.col("ts").dt.date())
    ).with_columns(((pl.col("bid") + pl.col("ask")) / 2).alias("mid"))
    rows = []
    for (ts,), snap in live.partition_by(["ts"], as_dict=True, maintain_order=True).items():
        pairs = snap.pivot(
            on="cp", index=["expiry_date", "strike"], values="mid", aggregate_function="mean"
        ).drop_nulls()
        if "C" not in pairs.columns or "P" not in pairs.columns:
            continue
        counts = pairs.group_by("expiry_date").agg(pl.len()).sort("expiry_date")
        eligible = counts.filter(pl.col("len") >= MIN_PARITY_STRIKES)
        if eligible.is_empty():
            continue
        mids = pairs.filter(pl.col("expiry_date") == eligible["expiry_date"][0]).sort("strike")
        fit = fit_parity(mids["strike"].to_numpy(), mids["C"].to_numpy(), mids["P"].to_numpy())
        if not (np.isfinite(fit.forward) and fit.df > 0):
            continue
        rows.append({"ts": ts, "spot": float(fit.forward * fit.df)})
    return pl.DataFrame(rows)


def build_rates(sessions: pl.DataFrame) -> pl.DataFrame:
    dtb3 = pl.read_parquet(DTB3).drop_nulls("rate_pct")
    joined = sessions.select(pl.col("session").alias("date")).join_asof(
        dtb3.sort("date"), on="date", strategy="backward"
    )
    # discount-basis T-bill quote -> continuously-compounded ACT/365 zero
    out = joined.select(
        "date",
        pl.lit(91, dtype=pl.Int64).alias("tenor_days"),
        (pl.col("rate_pct") / 100.0)
        .map_elements(
            lambda r: math.log(1.0 / (1.0 - r * 91.0 / 360.0)) / (91.0 / 365.0),
            return_dtype=pl.Float64,
        )
        .alias("rate"),
    )
    return validate_schema(out, RATES_SCHEMA, "theta_live rates")


def build_world(
    data_version: str = "theta_live_world_v1",
    out_root: Path = OUT_ROOT,
    start: dt.date = WINDOW_START,
    end: dt.date = WINDOW_END,
) -> dict:
    files = sorted(
        f
        for f in BARS_DIR.glob("date=*.parquet")
        if start <= dt.date.fromisoformat(f.stem.removeprefix("date=")) <= end
    )
    if not files:
        raise VendorError("no bars15 sessions in the live-world window")
    qdir = out_root / "option_quotes"
    sdir = out_root / "spots"
    qdir.mkdir(parents=True, exist_ok=True)
    sdir.mkdir(parents=True, exist_ok=True)

    # RESUMABLE: parity spots persist as per-session sidecars, so a crash in
    # the post-loop aggregation (seen once: silent OOM after 2600 sessions)
    # never re-costs the fit loop. quotes+spots present -> session skipped.
    bar_rows: list[pl.DataFrame] = []
    dates: list[dt.date] = []
    total = 0
    no_spot_ts = 0
    dropped_sessions: list[str] = []
    for f in files:
        date = dt.date.fromisoformat(f.stem.removeprefix("date="))
        qpath = qdir / f"date={date}.parquet"
        spath = sdir / f"date={date}.parquet"
        if qpath.exists() and spath.exists():
            spots = pl.read_parquet(spath)
            bar_rows.append(spots)
            dates.append(date)
            total += pl.scan_parquet(qpath).select(pl.len()).collect().item()
            continue
        if qpath.exists() and not spath.exists():
            # quotes saved by a previous run; recompute spots from them
            quotes = pl.read_parquet(qpath)
        else:
            quotes = to_quotes(pl.read_parquet(f))
        spots = parity_spots_for_session(quotes)
        # every stored quote snapshot MUST have an underlying bar (the engine
        # indexes bars by quote ts), so trim quotes to spot-bearing ts; a
        # session too thin to price spot at >=10 bars is dropped and named
        if spots.height < 10:
            dropped_sessions.append(str(date))
            continue
        no_spot_ts += quotes["ts"].n_unique() - spots.height
        quotes = quotes.filter(pl.col("ts").is_in(spots["ts"].to_list()))
        quotes.write_parquet(qpath)
        spots.write_parquet(spath)
        bar_rows.append(spots)
        dates.append(date)
        total += quotes.height
        if len(dates) % 100 == 0:
            print(f"  [{len(dates)}/{len(files)}] {date}", flush=True)

    if not bar_rows:
        raise VendorError("no session produced parity spots")
    spots_all = pl.concat(bar_rows).sort("ts")
    underlying = spots_all.select(
        "ts",
        pl.col("spot").alias("open"),
        pl.col("spot").alias("high"),
        pl.col("spot").alias("low"),
        pl.col("spot").alias("close"),
    )
    underlying.write_parquet(out_root / "underlying_bars.parquet")

    sessions = load_sessions(min(dates), max(dates)).filter(pl.col("session").is_in(dates))
    sessions.write_parquet(out_root / "sessions.parquet")

    # observed expiry table from the quotes themselves (vendor listing wins).
    # STREAMING per-file unique (a 2665-file lazy concat + collect died
    # silently at scale — likely memory): tiny set union instead.
    seen: set[tuple] = set()
    for d in dates:
        u = (
            pl.read_parquet(
                qdir / f"date={d}.parquet", columns=["expiry_date", "root", "am_pm_settle"]
            )
            .unique()
            .rows()
        )
        seen.update(u)
    expiries = (
        pl.DataFrame([{"expiry_date": e, "root": r, "settlement": s} for e, r, s in sorted(seen)])
        .select("expiry_date", "root", "settlement")
        .sort("expiry_date", "root")
    )
    validate_schema(expiries, EXPIRIES_SCHEMA, "theta_live expiries").write_parquet(
        out_root / "expiries.parquet"
    )

    # settlements: PM = last-bar parity spot of expiry session, AM = first-bar
    by_date = spots_all.with_columns(pl.col("ts").dt.date().alias("d"))
    first_last = by_date.group_by("d").agg(
        pl.col("spot").first().alias("am_spot"), pl.col("spot").last().alias("pm_spot")
    )
    settle = (
        expiries.join(first_last, left_on="expiry_date", right_on="d", how="inner")
        .with_columns(
            pl.when(pl.col("settlement") == "AM")
            .then(pl.col("am_spot"))
            .otherwise(pl.col("pm_spot"))
            .alias("value")
        )
        .select("expiry_date", "root", "settlement", "value")
        .sort("expiry_date", "root")
    )
    validate_schema(settle, SETTLEMENTS_SCHEMA, "theta_live settlements").write_parquet(
        out_root / "settlements.parquet"
    )

    build_rates(sessions).write_parquet(out_root / "rates.parquet")

    manifest = {
        "data_version": data_version,
        "label": (
            "REAL — ThetaData 15-min NBBO (bars15 decade extract); parity-derived "
            "spot/settlements; NOT synthetic"
        ),
        "vendor": "thetadata",
        "dataset": "live_world",
        "built_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window": [str(min(dates)), str(max(dates))],
        "fingerprint_window": ["2026-04-01", "2026-07-30"],
        "n_sessions": len(dates),
        "n_quote_rows": total,
        "snapshots_without_parity_spot_trimmed": no_spot_ts,
        "dropped_sessions": dropped_sessions,
        "proxies": [
            "per-bar OHLC = bar parity spot (no intra-bar extremes at 15-min NBBO)",
            "PM settlement = last-bar parity spot; AM (SET) = first-bar parity spot",
            "rates = FRED DTB3, single 91d tenor, cc ACT/365",
        ],
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-version", default="theta_live_world_v1")
    ap.add_argument("--out", default=str(OUT_ROOT))
    ap.add_argument("--start", default=str(WINDOW_START))
    ap.add_argument("--end", default=str(WINDOW_END))
    args = ap.parse_args()
    m = build_world(
        args.data_version,
        out_root=Path(args.out),
        start=dt.date.fromisoformat(args.start),
        end=dt.date.fromisoformat(args.end),
    )
    print(json.dumps({k: v for k, v in m.items() if k != "proxies"}, indent=2))


if __name__ == "__main__":
    main()
