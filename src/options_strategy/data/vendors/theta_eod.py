"""ThetaData FREE-tier EOD preview: fetch + packaging into a QA-able dataset.

Two of the six credit-check regimes (vix-spike-aug-2024, live-window-2026)
fall inside the free tier's EOD history (2023-06-01+). This module pulls the
closing-NBBO EOD reports for SPX + SPXW, DTE <= 63 (server-side), strikes
within +-15% of that session's ^GSPC close (client-side trim against the free
candle data), and packages them into the standard world layout so
``options_strategy qa`` runs unchanged.

Layout under data/raw/theta/eod_preview/ (gitignored — licensed data):
    raw/date=YYYY-MM-DD.parquet     vendor columns verbatim (+ root, window)
    world/manifest.json             data_version + provenance
    world/option_quotes/date=*.parquet   OPTION_QUOTES_SCHEMA, canonical close ts
    world/underlying_bars.parquet   ^GSPC daily OHLC at the same canonical ts
    world/sessions.parquet          XNYS-proxy sessions for the two windows

Usage (Theta Terminal running, free login is enough):

    python -m options_strategy.data.vendors.theta_eod --probe   # verify EOD has NBBO
    python -m options_strategy.data.vendors.theta_eod           # fetch (resumable)
    python -m options_strategy.data.vendors.theta_eod --world   # package for QA
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml

from options_strategy.data.calendar import load_sessions
from options_strategy.data.schemas import OPTION_QUOTES_SCHEMA, validate_schema
from options_strategy.data.vendors.thetadata import (
    RateLimiter,
    TerminalClient,
    TerminalError,
    _as_date,
)

DEFAULT_CONFIG = "configs/data/theta_eod_preview.yaml"

# Columns the internal mapping cannot do without. The vendor's EOD report
# carries more (OHLC, exchanges, conditions, report timestamps); the raw layer
# keeps everything verbatim.
EOD_REQUIRED = [
    "expiration",
    "strike",
    "right",
    "close",
    "volume",
    "bid",
    "bid_size",
    "ask",
    "ask_size",
]


@dataclass(frozen=True)
class Window:
    name: str
    start: dt.date
    end: dt.date


@dataclass(frozen=True)
class EodPreviewConfig:
    dataset: str
    out_root: Path
    base_url: str
    roots: tuple[str, ...]
    max_dte: int
    strike_window_pct: float
    rate_limit_per_min: int
    spot_source: Path
    windows: tuple[Window, ...]

    @staticmethod
    def load(path: str | Path) -> EodPreviewConfig:
        raw = yaml.safe_load(Path(path).read_text())
        return EodPreviewConfig(
            dataset=raw["dataset"],
            out_root=Path(raw["out_root"]),
            base_url=raw["terminal"]["base_url"].rstrip("/"),
            roots=tuple(raw["roots"]),
            max_dte=int(raw["max_dte"]),
            strike_window_pct=float(raw["strike_window_pct"]),
            rate_limit_per_min=int(raw["rate_limit_per_min"]),
            spot_source=Path(raw["spot_source"]),
            windows=tuple(
                Window(w["name"], _as_date(w["start"]), _as_date(w["end"]))
                for w in raw["windows"]
            ),
        )


def make_client(cfg: EodPreviewConfig) -> TerminalClient:
    return TerminalClient(cfg.base_url, limiter=RateLimiter(cfg.rate_limit_per_min))


def preview_sessions(cfg: EodPreviewConfig) -> pl.DataFrame:
    frames = [load_sessions(w.start, w.end) for w in cfg.windows]
    return pl.concat(frames).unique(subset="session").sort("session")


def load_spot_closes(cfg: EodPreviewConfig) -> dict[dt.date, float]:
    spot = pl.read_parquet(cfg.spot_source).select("date", "close")
    return dict(zip(spot["date"].to_list(), spot["close"].to_list(), strict=True))


def probe_eod(cfg: EodPreviewConfig, client: TerminalClient | None = None) -> dict:
    """Directive step 2: does the free EOD endpoint return the closing NBBO?

    Pulls one (root, date) report and inspects the columns. ``nbbo_ok`` False
    means quote-bearing preview work is BLOCKED until the paid month.
    """
    client = client or make_client(cfg)
    date = preview_sessions(cfg)["session"][0]
    df = client.eod_history(cfg.roots[0], date, cfg.max_dte)
    if df.is_empty():
        raise TerminalError(
            f"EOD probe returned no rows for {cfg.roots[0]} {date} — check login/tier"
        )
    missing = [c for c in EOD_REQUIRED if c not in df.columns]
    nonnull_quotes = (
        0
        if "bid" not in df.columns or "ask" not in df.columns
        else df.filter(pl.col("bid").is_not_null() & (pl.col("ask") > 0)).height
    )
    return {
        "probe_root": cfg.roots[0],
        "probe_date": str(date),
        "rows": df.height,
        "columns": df.columns,
        "missing_required": missing,
        "rows_with_live_nbbo": nonnull_quotes,
        "nbbo_ok": not missing and nonnull_quotes > 0,
    }


def fetch_preview(
    cfg: EodPreviewConfig, client: TerminalClient | None = None, force: bool = False
) -> dict:
    client = client or make_client(cfg)
    raw_dir = cfg.out_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sessions = preview_sessions(cfg)
    win_by_date = {
        d: w.name
        for w in cfg.windows
        for d in sessions.filter(
            pl.col("session").is_between(w.start, w.end)
        )["session"].to_list()
    }

    per_date: list[dict] = []
    for date, window in win_by_date.items():
        path = raw_dir / f"date={date}.parquet"
        if path.exists() and not force:
            n_rows = pl.scan_parquet(path).select(pl.len()).collect().item()
            per_date.append({"date": str(date), "rows": n_rows, "cached": True})
            continue
        frames = []
        for root in cfg.roots:
            df = client.eod_history(root, date, cfg.max_dte)
            if df.is_empty():
                continue
            missing = [c for c in EOD_REQUIRED if c not in df.columns]
            if missing:
                raise TerminalError(f"EOD response for {root} {date} missing {missing}")
            frames.append(
                df.with_columns(pl.lit(root).alias("root"), pl.lit(window).alias("window"))
            )
        if not frames:
            per_date.append({"date": str(date), "rows": 0, "cached": False})
            continue
        out = pl.concat(frames, how="diagonal")
        out.write_parquet(path)
        per_date.append({"date": str(date), "rows": out.height, "cached": False})
        print(f"  {date} [{window}]: {out.height} raw rows", flush=True)

    manifest = {
        "vendor": "thetadata",
        "dataset": cfg.dataset,
        "tier": "FREE (options EOD from 2023-06-01)",
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "license_note": "Licensed ThetaData data; data/raw/ is gitignored, never commit.",
        "roots": list(cfg.roots),
        "max_dte": cfg.max_dte,
        "n_sessions": len(win_by_date),
        "empty_sessions": [s["date"] for s in per_date if s["rows"] == 0],
        "total_raw_rows": sum(s["rows"] for s in per_date),
        "per_date": per_date,
    }
    (cfg.out_root / "raw_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _to_option_quotes(
    raw: pl.DataFrame, close_ts: dt.datetime, spot: float, strike_pct: float
) -> pl.DataFrame:
    """Map one session's raw vendor rows to OPTION_QUOTES_SCHEMA."""
    lo, hi = spot * (1 - strike_pct), spot * (1 + strike_pct)
    oi = (
        pl.col("open_interest").cast(pl.Int64, strict=False)
        if "open_interest" in raw.columns
        else pl.lit(None, dtype=pl.Int64)
    )
    out = (
        raw.filter(pl.col("strike").is_between(lo, hi))
        .with_columns(
            pl.col("expiration").cast(pl.Utf8).str.replace_all("-", "").str.to_date("%Y%m%d")
        )
        .select(
            pl.lit(close_ts).dt.replace_time_zone("America/New_York").alias("ts"),
            pl.col("root").cast(pl.String),
            pl.col("expiration").alias("expiry_date"),
            pl.when(pl.col("root") == "SPX")
            .then(pl.lit("AM"))
            .otherwise(pl.lit("PM"))
            .alias("am_pm_settle"),
            pl.col("strike").cast(pl.Float64),
            pl.col("right")
            .cast(pl.Utf8)
            .str.to_uppercase()
            .str.slice(0, 1)
            .alias("cp"),
            pl.col("bid").cast(pl.Float64),
            pl.col("ask").cast(pl.Float64),
            pl.col("bid_size").cast(pl.Int64),
            pl.col("ask_size").cast(pl.Int64),
            pl.col("close").cast(pl.Float64).alias("last"),
            pl.col("volume").cast(pl.Int64),
            oi.alias("open_interest"),
            pl.lit(0, dtype=pl.Int32).alias("quote_condition"),
        )
        .sort(["root", "expiry_date", "strike", "cp"])
    )
    return validate_schema(out, OPTION_QUOTES_SCHEMA, "theta_eod option_quotes")


def build_world(cfg: EodPreviewConfig, data_version: str) -> dict:
    """Package raw pulls into the standard world layout for the QA gate."""
    raw_dir = cfg.out_root / "raw"
    world = cfg.out_root / "world"
    qdir = world / "option_quotes"
    qdir.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(raw_dir.glob("date=*.parquet"))
    if not raw_files:
        raise FileNotFoundError(f"no raw pulls under {raw_dir} — run the fetch first")

    sessions = preview_sessions(cfg)
    spot_by_date = load_spot_closes(cfg)
    close_by_date = dict(
        zip(sessions["session"].to_list(), sessions["close_et"].to_list(), strict=True)
    )

    dates: list[dt.date] = []
    total_rows = 0
    for f in raw_files:
        date = dt.date.fromisoformat(f.stem.removeprefix("date="))
        if date not in spot_by_date:
            raise TerminalError(f"no ^GSPC close for {date} — refresh data/raw/free first")
        close_ts = close_by_date[date].replace(tzinfo=None)
        df = _to_option_quotes(
            pl.read_parquet(f), close_ts, spot_by_date[date], cfg.strike_window_pct
        )
        df.write_parquet(qdir / f"date={date}.parquet")
        dates.append(date)
        total_rows += df.height

    # sessions must cover exactly the sessions that have quote files, so the
    # QA "sessions_without_file" count reflects true vendor gaps, not scope.
    sessions.filter(pl.col("session").is_in(dates)).write_parquet(world / "sessions.parquet")

    gspc = pl.read_parquet(cfg.spot_source).filter(pl.col("date").is_in(dates))
    (
        gspc.select(
            pl.col("date")
            .map_elements(
                lambda d: close_by_date[d].replace(tzinfo=None),
                return_dtype=pl.Datetime("us"),
            )
            .dt.replace_time_zone("America/New_York")
            .alias("ts"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
        )
        .sort("ts")
        .write_parquet(world / "underlying_bars.parquet")
    )

    manifest = {
        "data_version": data_version,
        "vendor": "thetadata",
        "dataset": cfg.dataset,
        "kind": "REAL vendor EOD preview (2 of 6 credit-check regimes)",
        "built_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "underlying_note": (
            "underlying_bars = free ^GSPC daily OHLC (proxy, not SPX prints), "
            "one bar per session at the canonical close ts"
        ),
        "n_sessions": len(dates),
        "n_quote_rows": total_rows,
        "strike_window_pct": cfg.strike_window_pct,
        "max_dte": cfg.max_dte,
    }
    (world / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--probe", action="store_true", help="verify the EOD report carries NBBO")
    ap.add_argument("--world", action="store_true", help="package raw pulls for the QA gate")
    ap.add_argument("--data-version", default="theta_eod_preview_v1")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    cfg = EodPreviewConfig.load(args.config)
    if args.probe:
        result = probe_eod(cfg)
        print(json.dumps(result, indent=2))
        return 0 if result["nbbo_ok"] else 1
    if args.world:
        print(json.dumps(build_world(cfg, args.data_version), indent=2))
        return 0
    manifest = fetch_preview(cfg, force=args.force)
    print(json.dumps({k: v for k, v in manifest.items() if k != "per_date"}, indent=2))
    return 0 if not manifest["empty_sessions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
