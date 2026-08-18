"""Decade pull, item (b): 15-minute NBBO bars 2016-01-04 -> present.

One request per (root, session): option_history_quote(interval='15m',
expiration='*', max_dte=63, RTH). Client-side trim to strikes within ±15%
of that session's ^GSPC close (free candles; the plan's parity-derived-index
amendment covers intraday, daily close is enough for a strike window).

Resumable: one parquet per session under data/raw/theta/bars15/raw/;
sessions with a file are skipped. Disk is re-checked after the first ~5
sessions (chunk projection) per the 2026-08-18 directive.

Usage:  python -m options_strategy.data.vendors.theta_bars15 [--probe]
        [--start 2016-01-04] [--end <last ^GSPC session>]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import polars as pl

from options_strategy.data.calendar import load_sessions
from options_strategy.data.vendors.thetadata import (
    ThetaSession,
    VendorError,
    ensure_expiration_date,
    make_session,
)

OUT_ROOT = Path("data/raw/theta/bars15")
CREDS = Path("~/theta/creds.txt").expanduser()
GSPC = Path("data/raw/free/gspc_daily.parquet")
ROOTS = ("SPX", "SPXW")
MAX_DTE = 63
STRIKE_PCT = 0.15
INTERVAL = "15m"
DEFAULT_START = dt.date(2016, 1, 4)
MIN_FREE_GB = 40.0

QUOTE_COLS_REQUIRED = ["expiration", "strike", "right", "bid", "ask"]


def bars15_day(session: ThetaSession, root: str, day: dt.date) -> pl.DataFrame:
    return session._call(
        "option_history_quote",
        symbol=root,
        expiration="*",
        interval=INTERVAL,
        date=day,
        strike="*",
        right="both",
        max_dte=MAX_DTE,
    )


def spot_closes() -> dict[dt.date, float]:
    df = pl.read_parquet(GSPC).select("date", "close")
    return dict(zip(df["date"].to_list(), df["close"].to_list(), strict=True))


def fetch_day(session: ThetaSession, day: dt.date, spot: float) -> pl.DataFrame:
    lo, hi = spot * (1 - STRIKE_PCT), spot * (1 + STRIKE_PCT)
    frames = []
    for root in ROOTS:
        df = bars15_day(session, root, day)
        if df.is_empty():
            continue
        missing = [c for c in QUOTE_COLS_REQUIRED if c not in df.columns]
        if missing:
            raise VendorError(f"bars15 {root} {day}: missing columns {missing}")
        frames.append(
            ensure_expiration_date(df.with_columns(pl.col("strike").cast(pl.Float64)))
            .filter(pl.col("strike").is_between(lo, hi))
            .with_columns(pl.lit(root).alias("root"))
        )
    return pl.concat(frames, how="diagonal") if frames else pl.DataFrame()


def probe(session: ThetaSession, day: dt.date, spot: float) -> dict:
    df = fetch_day(session, day, spot)
    if df.is_empty():
        raise VendorError(f"15m probe empty on {day} — check interval string / tier")
    ts_col = next((c for c in df.columns if "time" in c.lower() or c == "timestamp"), None)
    return {
        "probe_date": str(day),
        "rows": df.height,
        "columns": df.columns,
        "n_contracts": df.select("root", "expiration", "strike", "right").unique().height,
        "bars_per_contract": round(
            df.height
            / max(df.select("root", "expiration", "strike", "right").unique().height, 1),
            1,
        ),
        "ts_column": ts_col,
    }


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def fetch_range(start: dt.date, end: dt.date, workers: int = 4) -> dict:
    """Days fan out over ``workers`` threads sharing ONE session (STANDARD
    allows 4 concurrent streams per session; a second login would kill the
    session — see ASSUMPTIONS 2026-08-18)."""
    from concurrent.futures import ThreadPoolExecutor

    session = make_session(CREDS, rate_limit_per_min=240)
    raw_dir = OUT_ROOT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    spots = spot_closes()
    days = [d for d in load_sessions(start, end)["session"].to_list() if d in spots]
    todo = [d for d in days if not (raw_dir / f"date={d}.parquet").exists()]
    done = len(days) - len(todo)
    fetched = 0
    bytes_new = 0

    failed: list[str] = []

    def pull_one(day: dt.date) -> tuple[dt.date, int, int]:
        try:
            df = fetch_day(session, day, spots[day])
        except VendorError as e:
            # one poisoned (root, day) must not kill a multi-day run; the
            # missing file makes the next resume retry it automatically
            failed.append(str(day))
            print(f"  {day}: FAILED after retries ({e})", flush=True)
            return day, 0, 0
        if df.is_empty():
            return day, 0, 0
        path = raw_dir / f"date={day}.parquet"
        df.write_parquet(path)
        return day, df.height, path.stat().st_size

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for day, n_rows, n_bytes in pool.map(pull_one, todo):
            if n_rows == 0:
                print(f"  {day}: EMPTY", flush=True)
                continue
            bytes_new += n_bytes
            fetched += 1
            if fetched in (5, 25) or fetched % 100 == 0:
                proj_gb = bytes_new / max(fetched, 1) * len(days) / 1e9
                print(
                    f"  [{done + fetched}/{len(days)}] {day}: {n_rows} rows; "
                    f"projected total ~{proj_gb:.1f} GB; free {free_gb(raw_dir):.0f} GB",
                    flush=True,
                )
                if free_gb(raw_dir) < MIN_FREE_GB:
                    raise VendorError(
                        f"free disk below {MIN_FREE_GB} GB safety floor — pull halted (resumable)"
                    )
    manifest = {
        "dataset": "bars15_decade",
        "interval": INTERVAL,
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "range": [str(start), str(end)],
        "n_sessions_total": len(days),
        "n_sessions_present": done + fetched,
        "failed_days": failed,
        "license_note": "Licensed ThetaData data; gitignored, never commit.",
    }
    (OUT_ROOT / "raw_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--start", default=str(DEFAULT_START))
    ap.add_argument("--end", default=None)
    args = ap.parse_args()
    spots = spot_closes()
    end = dt.date.fromisoformat(args.end) if args.end else max(spots)
    if args.probe:
        session = make_session(CREDS, rate_limit_per_min=240)
        day = max(d for d in spots if d <= end and d.weekday() == 4)
        print(json.dumps(probe(session, day, spots[day]), indent=2))
        return 0
    print(json.dumps(fetch_range(dt.date.fromisoformat(args.start), end), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
