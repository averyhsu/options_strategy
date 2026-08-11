"""Free daily-data fetch for the candle study (PLAN §8.3, amended 2026-08-10).

Downloads REAL free daily series into ``data/raw/free/`` (gitignored — raw
data never enters git; the repo is public):

- SPX daily candles 1995→present (yfinance ``^GSPC``; 1995 start gives the
  21-week EMA warm-up ahead of the 1999+ study window)
- CBOE daily VIX history (free CSV published by CBOE)
- FRED DTB3 (3M T-bill) and SOFR daily rates

This is the explicit user-approved Pass-1 exception (PLAN §12.0 pass-rules
clarification): the candle study is a data-replication study of the OP's
research process, not a strategy simulation. Free-data arrival does NOT
trigger Pass 2.

A ``manifest.json`` records source URLs, fetch time, row counts, and date
ranges so the report can label its sources precisely.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import urllib.request
from pathlib import Path

import polars as pl

GSPC_START = "1995-01-01"
VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

USER_AGENT = "options_strategy-research/0.1 (candle study; free public data)"


def _http_csv(url: str) -> pl.DataFrame:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return pl.read_csv(io.BytesIO(raw), infer_schema_length=10_000)


def fetch_gspc(out_dir: Path) -> dict:
    import yfinance as yf

    df = yf.download("^GSPC", start=GSPC_START, auto_adjust=False, progress=False, interval="1d")
    if df is None or len(df) == 0:
        raise RuntimeError("yfinance returned no ^GSPC rows")
    df = df.reset_index()
    # yfinance >= 0.2.40 returns MultiIndex columns (field, ticker) — flatten
    if hasattr(df.columns, "get_level_values") and df.columns.nlevels > 1:
        df.columns = [c[0] for c in df.columns]
    out = pl.DataFrame(
        {
            "date": [d.date() for d in df["Date"]],
            "open": df["Open"].astype(float).tolist(),
            "high": df["High"].astype(float).tolist(),
            "low": df["Low"].astype(float).tolist(),
            "close": df["Close"].astype(float).tolist(),
            "volume": df["Volume"].astype(float).tolist(),
        }
    ).sort("date")
    path = out_dir / "gspc_daily.parquet"
    out.write_parquet(path)
    return _entry("SPX daily candles (^GSPC)", "yfinance ^GSPC daily, unadjusted", out, path)


def fetch_vix(out_dir: Path) -> dict:
    df = _http_csv(VIX_URL)
    out = (
        df.rename({c: c.strip().lower() for c in df.columns})
        .with_columns(pl.col("date").str.to_date("%m/%d/%Y"))
        .sort("date")
    )
    path = out_dir / "vix_daily.parquet"
    out.write_parquet(path)
    return _entry("VIX daily history", VIX_URL, out, path)


def fetch_fred(series: str, out_dir: Path) -> dict:
    url = FRED_URL.format(series=series)
    df = _http_csv(url)
    date_col, val_col = df.columns[0], df.columns[1]
    out = (
        df.rename({date_col: "date", val_col: "rate_pct"})
        .with_columns(
            pl.col("date").cast(pl.Date),
            # FRED encodes missing observations as "."
            pl.col("rate_pct").cast(pl.Utf8).str.strip_chars().replace(".", None).cast(pl.Float64),
        )
        .sort("date")
    )
    path = out_dir / f"{series.lower()}_daily.parquet"
    out.write_parquet(path)
    return _entry(f"FRED {series}", url, out, path)


def _entry(name: str, source: str, df: pl.DataFrame, path: Path) -> dict:
    return {
        "name": name,
        "source": source,
        "path": path.name,
        "rows": df.height,
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
    }


def fetch_all(root: str | Path = "data/raw/free") -> dict:
    out_dir = Path(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        fetch_gspc(out_dir),
        fetch_vix(out_dir),
        fetch_fred("DTB3", out_dir),
        fetch_fred("SOFR", out_dir),
    ]
    manifest = {
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "note": (
            "Free public daily data for the candle study (PLAN §8.3). "
            "Gitignored; never committed (public repo). NOT purchased options "
            "data — does not trigger Pass 2."
        ),
        "series": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    print(json.dumps(fetch_all(), indent=2))
