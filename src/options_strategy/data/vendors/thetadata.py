"""ThetaData acquisition for the real-chain credit check slice.

Pulls SPX + SPXW NBBO quote snapshots from a locally running Theta Terminal
v3 (the vendor's Java gateway; it holds the account credentials — this module
only ever talks to 127.0.0.1). Sample plan comes from a YAML config
(configs/data/thetadata_credit_check_slice.yaml), transcribed from the
mini-purchase specification in reports/candle_study.md.

Requires an Options STANDARD subscription or better: the at_time snapshot
endpoint is Standard+, and Standard's options history starts 2016-01-01
(covers the 2017 sample dates).

Licensed vendor data: all output lands under data/raw/ (gitignored — the
repo is public; raw vendor data is never committed).

Usage (terminal must be running first):

    python -m options_strategy.data.vendors.thetadata --check
    python -m options_strategy.data.vendors.thetadata          # full pull, resumable
    python -m options_strategy.data.vendors.thetadata --force  # refetch everything

After a successful pull: run the data QA gate, commit the QA report, bump
data_version, rerun P2 invariants — only then strategy/eval runs (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml

DEFAULT_CONFIG = "configs/data/thetadata_credit_check_slice.yaml"

# v3 at_time/quote response columns we require, with target dtypes.
QUOTE_SCHEMA = {
    "symbol": pl.Utf8,
    "expiration": pl.Utf8,
    "strike": pl.Float64,
    "right": pl.Utf8,
    "timestamp": pl.Utf8,
    "bid_size": pl.Int64,
    "bid_exchange": pl.Utf8,
    "bid": pl.Float64,
    "bid_condition": pl.Utf8,
    "ask_size": pl.Int64,
    "ask_exchange": pl.Utf8,
    "ask": pl.Float64,
    "ask_condition": pl.Utf8,
}


@dataclass(frozen=True)
class SampleDate:
    window: str
    entry_date: dt.date
    spot: float
    ema_state: str
    strike_lo: float
    strike_hi: float


@dataclass(frozen=True)
class SliceConfig:
    dataset: str
    out_root: Path
    base_url: str
    roots: tuple[str, ...]
    max_dte: int
    snapshot_times: tuple[str, ...]
    primary_snapshot: str
    strike_pad_points: float
    samples: tuple[SampleDate, ...]

    @staticmethod
    def load(path: str | Path) -> SliceConfig:
        raw = yaml.safe_load(Path(path).read_text())
        samples = tuple(
            SampleDate(
                window=s["window"],
                entry_date=_as_date(s["entry_date"]),
                spot=float(s["spot"]),
                ema_state=s["ema_state"],
                strike_lo=float(s["strike_lo"]),
                strike_hi=float(s["strike_hi"]),
            )
            for s in raw["samples"]
        )
        return SliceConfig(
            dataset=raw["dataset"],
            out_root=Path(raw["out_root"]),
            base_url=raw["terminal"]["base_url"].rstrip("/"),
            roots=tuple(raw["roots"]),
            max_dte=int(raw["max_dte"]),
            snapshot_times=tuple(raw["snapshot_times"]),
            primary_snapshot=raw["primary_snapshot"],
            strike_pad_points=float(raw["strike_pad_points"]),
            samples=samples,
        )


def _as_date(v: object) -> dt.date:
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def _yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


class TerminalError(RuntimeError):
    pass


class RateLimiter:
    """Spaces requests to at most ``per_min`` per minute (free tier: 30/min).

    ``clock``/``sleeper`` are injectable so tests never actually wait.
    """

    def __init__(
        self,
        per_min: int,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = 60.0 / per_min
        self._clock = clock
        self._sleep = sleeper
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            remaining = self.interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last = now


class TerminalClient:
    """Thin HTTP client for the local Theta Terminal v3.

    ``fetch`` is injectable so tests never touch the network.
    """

    def __init__(
        self,
        base_url: str,
        fetch: Callable[[str], bytes] | None = None,
        retries: int = 3,
        backoff_s: float = 2.0,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._fetch = fetch if fetch is not None else self._http_get
        self.retries = retries
        self.backoff_s = backoff_s
        self.limiter = limiter

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"Accept": "text/csv"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()

    def _get_csv(self, path: str, params: dict[str, str]) -> pl.DataFrame:
        if self.limiter is not None:
            self.limiter.wait()
        query = urllib.parse.urlencode({**params, "format": "csv"})
        url = f"{self.base_url}{path}?{query}"
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                raw = self._fetch(url)
                if not raw.strip():
                    return pl.DataFrame()
                return pl.read_csv(io.BytesIO(raw), infer_schema_length=10_000)
            except urllib.error.HTTPError as e:
                # 472 is the vendor's NO_DATA; treat as empty, not an error.
                if e.code == 472:
                    return pl.DataFrame()
                last_err = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
            time.sleep(self.backoff_s * (attempt + 1))
        raise TerminalError(
            f"terminal request failed after {self.retries} tries: {url}\n{last_err}"
        )

    def list_expirations(self, root: str) -> list[dt.date]:
        df = self._get_csv("/v3/option/list/expirations", {"symbol": root})
        if df.is_empty():
            return []
        col = "expiration" if "expiration" in df.columns else df.columns[-1]
        return sorted(_as_date(v) for v in df[col].unique().to_list())

    def eod_history(self, root: str, date: dt.date, max_dte: int) -> pl.DataFrame:
        """Free-tier EOD report (OHLC + closing NBBO) for every contract of a
        root on one session, all expiries within max_dte. One request per
        (root, date) keeps the server-side max_dte filter unambiguous."""
        return self._get_csv(
            "/v3/option/history/eod",
            {
                "symbol": root,
                "expiration": "*",
                "start_date": _yyyymmdd(date),
                "end_date": _yyyymmdd(date),
                "max_dte": str(max_dte),
                "strike": "*",
                "right": "both",
            },
        )

    def at_time_quote(
        self, root: str, expiration: dt.date, date: dt.date, time_of_day: str
    ) -> pl.DataFrame:
        return self._get_csv(
            "/v3/option/at_time/quote",
            {
                "symbol": root,
                "expiration": _yyyymmdd(expiration),
                "start_date": _yyyymmdd(date),
                "end_date": _yyyymmdd(date),
                "time_of_day": f"{time_of_day}.000",
                "strike": "*",
                "right": "both",
            },
        )


def _normalize(df: pl.DataFrame, root: str, snap_time: str, sample: SampleDate) -> pl.DataFrame:
    missing = [c for c in QUOTE_SCHEMA if c not in df.columns]
    if missing:
        raise TerminalError(f"quote response missing columns {missing}; got {df.columns}")
    return (
        df.select(
            [pl.col(c).cast(t, strict=False) for c, t in QUOTE_SCHEMA.items()]
        )
        .with_columns(
            pl.col("expiration").str.replace_all("-", "").str.to_date("%Y%m%d"),
            pl.lit(root).alias("root"),
            pl.lit(sample.entry_date).alias("entry_date"),
            pl.lit(snap_time).alias("snapshot_et"),
            pl.lit(sample.window).alias("regime_window"),
            pl.lit(sample.ema_state).alias("ema_state"),
        )
    )


def expiries_in_scope(all_exps: list[dt.date], sample_date: dt.date, max_dte: int) -> list[dt.date]:
    """Listed expiries with 0 < DTE <= max_dte calendar days from the sample date."""
    return [e for e in all_exps if 0 < (e - sample_date).days <= max_dte]


def fetch_sample_date(
    client: TerminalClient,
    cfg: SliceConfig,
    sample: SampleDate,
    exps_by_root: dict[str, list[dt.date]],
) -> pl.DataFrame:
    lo = sample.strike_lo - cfg.strike_pad_points
    hi = sample.strike_hi + cfg.strike_pad_points
    frames: list[pl.DataFrame] = []
    for root in cfg.roots:
        for exp in expiries_in_scope(exps_by_root[root], sample.entry_date, cfg.max_dte):
            for snap_time in cfg.snapshot_times:
                df = client.at_time_quote(root, exp, sample.entry_date, snap_time)
                if df.is_empty():
                    continue
                frames.append(
                    _normalize(df, root, snap_time, sample).filter(
                        pl.col("strike").is_between(lo, hi)
                    )
                )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="vertical").sort(
        ["root", "expiration", "strike", "right", "snapshot_et"]
    )


def _date_stats(df: pl.DataFrame, sample: SampleDate) -> dict:
    if df.is_empty():
        return {"entry_date": str(sample.entry_date), "window": sample.window, "rows": 0}
    crossed = df.filter(
        (pl.col("bid") > pl.col("ask")) & (pl.col("bid") > 0) & (pl.col("ask") > 0)
    ).height
    return {
        "entry_date": str(sample.entry_date),
        "window": sample.window,
        "rows": df.height,
        "roots": sorted(df["root"].unique().to_list()),
        "n_expiries": df["expiration"].n_unique(),
        "expiry_min": str(df["expiration"].min()),
        "expiry_max": str(df["expiration"].max()),
        "strike_min": df["strike"].min(),
        "strike_max": df["strike"].max(),
        "n_snapshots": df["snapshot_et"].n_unique(),
        "crossed_quotes": crossed,
        "zero_bids": df.filter(pl.col("bid") <= 0).height,
    }


def check_terminal(cfg: SliceConfig, client: TerminalClient | None = None) -> dict:
    """Reachability + subscription sanity: can we see 2017 SPX quote history?"""
    client = client or TerminalClient(cfg.base_url)
    out: dict = {"base_url": cfg.base_url}
    exps = client.list_expirations("SPXW")
    out["spxw_expirations_listed"] = len(exps)
    if not exps:
        raise TerminalError("terminal reachable but listed no SPXW expirations")
    earliest = cfg.samples[0]
    probe_exps = expiries_in_scope(client.list_expirations("SPX"), earliest.entry_date, 40)
    out["probe_date"] = str(earliest.entry_date)
    probe_rows = 0
    for exp in probe_exps[:3]:
        snap = client.at_time_quote("SPX", exp, earliest.entry_date, cfg.primary_snapshot)
        probe_rows += snap.height
    out["probe_rows_2017"] = probe_rows
    out["history_ok"] = probe_rows > 0
    if probe_rows == 0:
        out["note"] = (
            "No 2017 quote rows returned — subscription tier likely below Options "
            "STANDARD (Value history starts 2020-01-01). Upgrade before the full pull."
        )
    return out


def fetch_slice(
    cfg: SliceConfig, client: TerminalClient | None = None, force: bool = False
) -> dict:
    client = client or TerminalClient(cfg.base_url)
    out_dir = cfg.out_root / "quotes"
    out_dir.mkdir(parents=True, exist_ok=True)
    exps_by_root = {root: client.list_expirations(root) for root in cfg.roots}
    for root, exps in exps_by_root.items():
        if not exps:
            raise TerminalError(f"no expirations listed for root {root}")

    per_date: list[dict] = []
    for sample in cfg.samples:
        path = out_dir / f"{sample.entry_date}.parquet"
        if path.exists() and not force:
            per_date.append(_date_stats(pl.read_parquet(path), sample))
            continue
        df = fetch_sample_date(client, cfg, sample, exps_by_root)
        stats = _date_stats(df, sample)
        if df.is_empty():
            # Leave no file so a rerun retries this date; record the gap.
            per_date.append(stats)
            continue
        df.write_parquet(path)
        per_date.append(stats)
        print(f"  {sample.entry_date} [{sample.window}]: {stats['rows']} rows", flush=True)

    total_rows = sum(s["rows"] for s in per_date)
    empty_dates = [s["entry_date"] for s in per_date if s["rows"] == 0]
    manifest = {
        "vendor": "thetadata",
        "dataset": cfg.dataset,
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "terminal": cfg.base_url,
        "spec_source": "reports/candle_study.md mini-purchase specification (51 sample dates)",
        "license_note": (
            "Licensed ThetaData subscription data. data/raw/ is gitignored; "
            "never commit (public repo, PLAN.md §15)."
        ),
        "roots": list(cfg.roots),
        "max_dte": cfg.max_dte,
        "snapshot_times_et": list(cfg.snapshot_times),
        "primary_snapshot_et": cfg.primary_snapshot,
        "strike_pad_points": cfg.strike_pad_points,
        "n_sample_dates": len(cfg.samples),
        "n_dates_with_data": sum(1 for s in per_date if s["rows"] > 0),
        "empty_dates": empty_dates,
        "total_rows": total_rows,
        "per_date": per_date,
    }
    (cfg.out_root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument(
        "--check", action="store_true", help="terminal + subscription sanity check only"
    )
    ap.add_argument(
        "--force", action="store_true", help="refetch dates that already have parquet files"
    )
    args = ap.parse_args(argv)

    cfg = SliceConfig.load(args.config)
    if args.check:
        print(json.dumps(check_terminal(cfg), indent=2))
        return 0
    manifest = fetch_slice(cfg, force=args.force)
    print(json.dumps({k: v for k, v in manifest.items() if k != "per_date"}, indent=2))
    if manifest["empty_dates"]:
        print(f"WARNING: {len(manifest['empty_dates'])} sample dates returned no rows: "
              f"{manifest['empty_dates']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
