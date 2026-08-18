"""Touch-week tick pull, item (c): NBBO ticks for the traded legs of every
defense-activation week.

Week list (2026-08-18 amendment): UNION of q85/q90/q95 put/call touches —
above-EMA entry weeks (candle-study machinery, free ^GSPC daily) whose next
week's extremes touched a band edge — restricted to 2016+ (STANDARD floor).

Per touch week: 8 contracts — front-expiry shorts at the q85/q90/q95 put and
call edge strikes (6, roll candidates included) + back-expiry q90±25 wings
(2). Days: entry Friday through the front expiry (the defense window).
Expiries resolve against the vendor's listed SPXW expirations (holiday
shifts included).

Disk rule: after a ~40-contract-day sample the total is projected; above
~100 GB projected, quote-change-only dedup is applied to every stored day.

Resumable: one parquet per week under data/raw/theta/ticks/weeks/.

Usage:  python -m options_strategy.data.vendors.theta_ticks [--probe] [--list-only]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy.data.calendar import load_sessions
from options_strategy.data.vendors.thetadata import (
    ThetaSession,
    VendorError,
    make_session,
)
from options_strategy.eval.candle_study import weekly_conditional_frame

OUT_ROOT = Path("data/raw/theta/ticks")
CREDS = Path("~/theta/creds.txt").expanduser()
GSPC = Path("data/raw/free/gspc_daily.parquet")
QS = (0.85, 0.90, 0.95)
FLOOR = dt.date(2016, 1, 4)
TICK_INTERVAL = "tick"
DEDUP_THRESHOLD_GB = 100.0
ROOT = "SPXW"


def _round5(x: float) -> float:
    return float(round(x / 5.0) * 5.0)


def touch_week_frame() -> pl.DataFrame:
    """Above-EMA entry weeks 2016+ with q85-q95 union touch flags + edge strikes."""
    daily = (
        pl.read_parquet(GSPC)
        .rename({"date": "session"})
        .select("session", "open", "high", "low", "close")
    )
    wk = weekly_conditional_frame(daily)
    above = wk.filter(pl.col("state") == "bull")
    rets = above["next_ret"].to_numpy()
    edges = {q: (float(np.quantile(rets, 1 - q)), float(np.quantile(rets, q))) for q in QS}
    out = above.select("week_end", "close", "next_low_ret", "next_high_ret")
    touch_any = pl.lit(False)
    for q, (pe, ce) in edges.items():
        tag = f"q{int(q * 100)}"
        out = out.with_columns(
            (pl.col("next_low_ret") <= pe).alias(f"touch_put_{tag}"),
            (pl.col("next_high_ret") >= ce).alias(f"touch_call_{tag}"),
            (pl.col("close") * (1 + pe))
            .map_elements(_round5, return_dtype=pl.Float64)
            .alias(f"k_put_{tag}"),
            (pl.col("close") * (1 + ce))
            .map_elements(_round5, return_dtype=pl.Float64)
            .alias(f"k_call_{tag}"),
        )
        touch_any = touch_any | pl.col(f"touch_put_{tag}") | pl.col(f"touch_call_{tag}")
    return (
        out.with_columns(touch_any.alias("touched"))
        .filter(pl.col("touched") & (pl.col("week_end") >= FLOOR))
        .sort("week_end")
    )


def resolve_expiries(week_end: dt.date, listed: list[dt.date]) -> tuple[dt.date, dt.date] | None:
    """Front = the listed expiry CLOSEST to entry+7 days within [5, 9]
    (ties -> later date). A plain min-in-window pick grabs the Wednesday
    weekly at +5 and silently shortens the front tenor and defense window —
    caught 2026-08-18 on the tick pull."""
    window = [e for e in listed if 5 <= (e - week_end).days <= 9]
    if not window:
        return None
    front = min(window, key=lambda e: (abs((e - week_end).days - 7), -(e - week_end).days))
    back = next((e for e in listed if (e - front).days >= 21), None)
    return None if back is None else (front, back)


def week_contracts(row: dict, front: dt.date, back: dt.date) -> list[dict]:
    legs = []
    for q in QS:
        tag = f"q{int(q * 100)}"
        legs.append({"expiration": front, "strike": row[f"k_put_{tag}"], "right": "put"})
        legs.append({"expiration": front, "strike": row[f"k_call_{tag}"], "right": "call"})
    legs.append({"expiration": back, "strike": row["k_put_q90"] - 25.0, "right": "put"})
    legs.append({"expiration": back, "strike": row["k_call_q90"] + 25.0, "right": "call"})
    # dedupe (q-levels can round to the same strike)
    seen, out = set(), []
    for leg in legs:
        key = (leg["expiration"], leg["strike"], leg["right"])
        if key not in seen:
            seen.add(key)
            out.append(leg)
    return out


def tick_day(session: ThetaSession, leg: dict, day: dt.date) -> pl.DataFrame:
    return session._call(
        "option_history_quote",
        symbol=ROOT,
        expiration=leg["expiration"],
        interval=TICK_INTERVAL,
        date=day,
        strike=f"{leg['strike']:g}",
        right=leg["right"],
    )


def dedup_quote_changes(df: pl.DataFrame) -> pl.DataFrame:
    cols = [c for c in ("bid", "ask", "bid_size", "ask_size") if c in df.columns]
    if not cols:
        return df
    changed = pl.any_horizontal([pl.col(c) != pl.col(c).shift(1) for c in cols])
    return df.filter(changed.fill_null(True))


def fetch_weeks(limit: int | None = None) -> dict:
    session = make_session(CREDS, rate_limit_per_min=240)
    weeks = touch_week_frame()
    listed = session.list_expirations(ROOT)
    out_dir = OUT_ROOT / "weeks"
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions_all = load_sessions(FLOOR, max(listed))

    dedup = False
    bytes_done = 0
    weeks_done = 0
    skipped: list[str] = []
    failed_requests: list[str] = []
    rows_iter = weeks.head(limit).rows(named=True) if limit else weeks.rows(named=True)
    total_weeks = min(limit, weeks.height) if limit else weeks.height
    for row in rows_iter:
        week_end = row["week_end"]
        path = out_dir / f"week={week_end}.parquet"
        if path.exists():
            weeks_done += 1
            bytes_done += path.stat().st_size
            continue
        exps = resolve_expiries(week_end, listed)
        if exps is None:
            skipped.append(str(week_end))
            continue
        front, back = exps
        days = sessions_all.filter(
            (pl.col("session") >= week_end) & (pl.col("session") <= front)
        )["session"].to_list()
        frames = []
        for leg in week_contracts(row, front, back):
            for day in days:
                try:
                    df = tick_day(session, leg, day)
                except VendorError as e:
                    # vendor-side 500s on single contract-days (observed:
                    # ArrayIndexOutOfBoundsException) must not kill the run
                    tag = f"{week_end}:{leg['expiration']}:{leg['strike']:g}{leg['right'][0]}:{day}"
                    failed_requests.append(tag)
                    print(f"  REQUEST FAILED {tag} ({type(e).__name__})", flush=True)
                    continue
                if df.is_empty():
                    continue
                if dedup:
                    df = dedup_quote_changes(df)
                frames.append(
                    df.with_columns(
                        pl.lit(week_end).alias("touch_week"),
                        pl.lit(day).alias("day"),
                        pl.lit(leg["expiration"]).alias("leg_expiration"),
                        pl.lit(leg["strike"]).alias("leg_strike"),
                        pl.lit(leg["right"]).alias("leg_right"),
                    )
                )
        if not frames:
            skipped.append(str(week_end))
            continue
        wk_df = pl.concat(frames, how="diagonal")
        wk_df.write_parquet(path)
        weeks_done += 1
        bytes_done += path.stat().st_size
        if shutil.disk_usage(out_dir).free / 1e9 < 40.0:
            raise VendorError("free disk below 40 GB safety floor — tick pull halted (resumable)")
        proj_gb = bytes_done / weeks_done * total_weeks / 1e9
        if weeks_done % 10 == 1:
            print(
                f"  [{weeks_done}/{total_weeks}] {week_end}: {wk_df.height} ticks; "
                f"projected ~{proj_gb:.1f} GB (dedup={'on' if dedup else 'off'})",
                flush=True,
            )
        if not dedup and proj_gb > DEDUP_THRESHOLD_GB:
            dedup = True
            print(f"  projection {proj_gb:.0f} GB > {DEDUP_THRESHOLD_GB} GB: dedup ON", flush=True)

    manifest = {
        "dataset": "touch_week_ticks",
        "interval": TICK_INTERVAL,
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "n_touch_weeks": weeks.height,
        "n_weeks_stored": weeks_done,
        "skipped_weeks": skipped,
        "failed_requests": failed_requests,
        "dedup_applied": dedup,
        "bytes_total": bytes_done,
        "license_note": "Licensed ThetaData data; gitignored, never commit.",
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="one contract-day tick request")
    ap.add_argument("--list-only", action="store_true", help="print the touch-week count")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.list_only:
        weeks = touch_week_frame()
        print(json.dumps({
            "n_touch_weeks": weeks.height,
            "first": str(weeks["week_end"].min()),
            "last": str(weeks["week_end"].max()),
        }, indent=2))
        return 0
    if args.probe:
        session = make_session(CREDS, rate_limit_per_min=240)
        weeks = touch_week_frame()
        row = weeks.row(-1, named=True)
        listed = session.list_expirations(ROOT)
        exps = resolve_expiries(row["week_end"], listed)
        if exps is None:
            raise VendorError("probe: could not resolve expiries")
        leg = week_contracts(row, *exps)[0]
        df = tick_day(session, leg, row["week_end"])
        print(json.dumps({
            "week": str(row["week_end"]), "leg": {k: str(v) for k, v in leg.items()},
            "rows": df.height, "columns": df.columns,
        }, indent=2))
        return 0
    print(json.dumps(fetch_weeks(limit=args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
