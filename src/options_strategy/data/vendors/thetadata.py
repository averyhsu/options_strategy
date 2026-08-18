"""ThetaData acquisition via the OFFICIAL Python library (no Theta Terminal).

Transport: ``thetadata.ThetaClient`` (pip ``thetadata>=1.0.10``) — authenticates
over HTTPS and streams data over gRPC directly from the vendor
(user directive 2026-08-17; replaces the Theta Terminal v3 REST gateway whose
bootstrap backend proved fragile). Credentials come from a creds file
(email line 1, password line 2) whose PATH is configured here; its contents
are never read, logged, or committed by this codebase.

This module owns the shared plumbing plus the paid-month at_time slice
fetcher (spec: reports/candle_study.md mini-purchase table, 51 sample dates).
The free-tier EOD preview lives in theta_eod.py.

Requires Options STANDARD or better for the at_time slice: at_time endpoints
are Standard+, and Standard's options history starts 2016-01-01 (covers the
2017 sample dates). ``check_access`` verifies both before a full pull.

Licensed vendor data: all output lands under data/raw/ (gitignored — the
repo is public; raw vendor data is never committed).

Usage:

    python -m options_strategy.data.vendors.thetadata --check
    python -m options_strategy.data.vendors.thetadata          # full pull, resumable
    python -m options_strategy.data.vendors.thetadata --force  # refetch everything

After a successful pull: run the data QA gate, commit the QA report, bump
data_version, rerun P2 invariants — only then strategy/eval runs (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml

DEFAULT_CONFIG = "configs/data/thetadata_credit_check_slice.yaml"

# at_time quote response columns the slice cannot do without (per the v3 API
# the library mirrors); extra vendor columns are preserved in the raw layer.
QUOTE_REQUIRED = ["expiration", "strike", "right", "bid", "bid_size", "ask", "ask_size"]


class VendorError(RuntimeError):
    pass


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
    creds_file: Path
    roots: tuple[str, ...]
    max_dte: int
    snapshot_times: tuple[str, ...]
    primary_snapshot: str
    strike_pad_points: float
    rate_limit_per_min: int
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
            creds_file=Path(raw["auth"]["creds_file"]).expanduser(),
            roots=tuple(raw["roots"]),
            max_dte=int(raw["max_dte"]),
            snapshot_times=tuple(raw["snapshot_times"]),
            primary_snapshot=raw["primary_snapshot"],
            strike_pad_points=float(raw["strike_pad_points"]),
            rate_limit_per_min=int(raw.get("rate_limit_per_min", 28)),
            samples=samples,
        )


def _as_date(v: object) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


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


def make_library_client(creds_file: Path):
    """Construct the official client (polars frames). Lazy import so the
    engine and offline tests never need the vendor package installed."""
    from thetadata import ThetaClient

    return ThetaClient(creds_file=str(creds_file), dataframe_type="polars")


class ThetaSession:
    """Rate-limited, retrying wrapper around the official ThetaClient.

    ``client`` is injectable so tests use a fake with the same three methods.
    NoDataFoundError is normalized to an empty frame (an expiry that was not
    listed on a historical date is data absence, not an error).
    """

    def __init__(
        self,
        client,
        limiter: RateLimiter | None = None,
        retries: int = 3,
        backoff_s: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.limiter = limiter
        self.retries = retries
        self.backoff_s = backoff_s
        self._sleep = sleeper

    def _call(self, method: str, **kwargs) -> pl.DataFrame:
        if self.limiter is not None:
            self.limiter.wait()
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                out = getattr(self.client, method)(**kwargs)
                return out if isinstance(out, pl.DataFrame) else pl.DataFrame(out)
            except Exception as e:  # vendor lib: NoDataFoundError / grpc.RpcError
                name = type(e).__name__
                if name == "NoDataFoundError":
                    return pl.DataFrame()
                if name == "AuthenticationError":
                    raise VendorError(f"authentication failed: {e}") from e
                last_err = e
            self._sleep(self.backoff_s * (attempt + 1))
        raise VendorError(f"{method}({kwargs}) failed after {self.retries} tries: {last_err}")

    def subscriptions(self) -> dict:
        """Access levels reported by the auth handshake (tier verification)."""
        return {
            "options": getattr(self.client, "options_subscription", None),
            "stock": getattr(self.client, "stock_subscription", None),
            "index": getattr(self.client, "index_subscription", None),
        }

    def list_expirations(self, root: str) -> list[dt.date]:
        df = self._call("option_list_expirations", symbol=root)
        if df.is_empty():
            return []
        col = "expiration" if "expiration" in df.columns else df.columns[-1]
        return sorted({_as_date(v) for v in df[col].to_list()})

    def eod_history(self, root: str, date: dt.date, max_dte: int) -> pl.DataFrame:
        """Free-tier EOD report (OHLC + closing NBBO) for every contract of a
        root on one session, all expiries within max_dte. One request per
        (root, date) keeps the server-side max_dte filter unambiguous."""
        return self._call(
            "option_history_eod",
            symbol=root,
            start_date=date,
            end_date=date,
            expiration="*",
            strike="*",
            right="both",
            max_dte=max_dte,
        )

    def at_time_quote(
        self, root: str, expiration: dt.date, date: dt.date, time_of_day: str
    ) -> pl.DataFrame:
        """NBBO snapshot at a minute-boundary ET time (Standard+)."""
        return self._call(
            "option_at_time_quote",
            symbol=root,
            start_date=date,
            end_date=date,
            time_of_day=time_of_day,
            expiration=expiration,
            strike="*",
            right="both",
        )


def make_session(creds_file: Path, rate_limit_per_min: int) -> ThetaSession:
    return ThetaSession(
        make_library_client(creds_file), limiter=RateLimiter(rate_limit_per_min)
    )


def ensure_expiration_date(df: pl.DataFrame) -> pl.DataFrame:
    """Vendor frames may carry expiration as Date, Datetime, or string."""
    dtype = df.schema["expiration"]
    if dtype == pl.Date:
        return df
    if isinstance(dtype, pl.Datetime):
        return df.with_columns(pl.col("expiration").dt.date())
    return df.with_columns(
        pl.col("expiration").cast(pl.Utf8).str.replace_all("-", "").str.to_date("%Y%m%d")
    )


def require_columns(df: pl.DataFrame, required: list[str], what: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise VendorError(f"{what} response missing columns {missing}; got {df.columns}")


def expiries_in_scope(all_exps: list[dt.date], sample_date: dt.date, max_dte: int) -> list[dt.date]:
    """Listed expiries with 0 < DTE <= max_dte calendar days from the sample date."""
    return [e for e in all_exps if 0 < (e - sample_date).days <= max_dte]


def _normalize(df: pl.DataFrame, root: str, snap_time: str, sample: SampleDate) -> pl.DataFrame:
    require_columns(df, QUOTE_REQUIRED, "at_time quote")
    return ensure_expiration_date(df).with_columns(
        pl.col("strike").cast(pl.Float64),
        pl.lit(root).alias("root"),
        pl.lit(sample.entry_date).alias("entry_date"),
        pl.lit(snap_time).alias("snapshot_et"),
        pl.lit(sample.window).alias("regime_window"),
        pl.lit(sample.ema_state).alias("ema_state"),
    )


def fetch_sample_date(
    session: ThetaSession,
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
                df = session.at_time_quote(root, exp, sample.entry_date, snap_time)
                if df.is_empty():
                    continue
                frames.append(
                    _normalize(df, root, snap_time, sample).filter(
                        pl.col("strike").is_between(lo, hi)
                    )
                )
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal").sort(
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


def check_access(cfg: SliceConfig, session: ThetaSession | None = None) -> dict:
    """Auth + tier + history-depth sanity for the paid-month slice: report the
    subscriptions the auth handshake grants, and probe a 2017 quote (Standard
    history starts 2016-01-01; Value would return nothing there)."""
    session = session or make_session(cfg.creds_file, cfg.rate_limit_per_min)
    out: dict = {"subscriptions": session.subscriptions()}
    exps = session.list_expirations("SPXW")
    out["spxw_expirations_listed"] = len(exps)
    if not exps:
        raise VendorError("authenticated but no SPXW expirations listed")
    earliest = cfg.samples[0]
    probe_exps = expiries_in_scope(session.list_expirations("SPX"), earliest.entry_date, 40)
    out["probe_date"] = str(earliest.entry_date)
    probe_rows = 0
    for exp in probe_exps[:3]:
        probe_rows += session.at_time_quote(
            "SPX", exp, earliest.entry_date, cfg.primary_snapshot
        ).height
    out["probe_rows_2017"] = probe_rows
    out["history_ok"] = probe_rows > 0
    if probe_rows == 0:
        out["note"] = (
            "No 2017 quote rows — subscription below Options STANDARD "
            "(Value history starts 2020-01-01) or at_time not included. "
            "Upgrade before the full slice pull."
        )
    return out


def fetch_slice(
    cfg: SliceConfig, session: ThetaSession | None = None, force: bool = False
) -> dict:
    session = session or make_session(cfg.creds_file, cfg.rate_limit_per_min)
    out_dir = cfg.out_root / "quotes"
    out_dir.mkdir(parents=True, exist_ok=True)
    exps_by_root = {root: session.list_expirations(root) for root in cfg.roots}
    for root, exps in exps_by_root.items():
        if not exps:
            raise VendorError(f"no expirations listed for root {root}")

    per_date: list[dict] = []
    for sample in cfg.samples:
        path = out_dir / f"{sample.entry_date}.parquet"
        if path.exists() and not force:
            per_date.append(_date_stats(pl.read_parquet(path), sample))
            continue
        df = fetch_sample_date(session, cfg, sample, exps_by_root)
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
        "transport": "official python library (gRPC, no terminal)",
        "dataset": cfg.dataset,
        "fetched_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
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
        "--check", action="store_true", help="auth + tier + history-depth sanity check only"
    )
    ap.add_argument(
        "--force", action="store_true", help="refetch dates that already have parquet files"
    )
    args = ap.parse_args(argv)

    cfg = SliceConfig.load(args.config)
    if args.check:
        print(json.dumps(check_access(cfg), indent=2, default=str))
        return 0
    manifest = fetch_slice(cfg)
    print(json.dumps({k: v for k, v in manifest.items() if k != "per_date"}, indent=2))
    if manifest["empty_dates"]:
        print(
            f"WARNING: {len(manifest['empty_dates'])} sample dates returned no rows: "
            f"{manifest['empty_dates']}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
