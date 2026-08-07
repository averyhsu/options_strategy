"""Synthetic world orchestrator: generate + write a full internal-schema
dataset with truth tables (PLAN §5, schemas §4.1).

Everything written here is SYNTHETIC (manifest carries the banner; world names
must contain "synthetic"). Outputs are bit-deterministic for a fixed config:
fixed RNG streams, fixed row ordering, and no wall-clock anywhere in the files.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy import __version__
from options_strategy.config import canonical_json, config_hash
from options_strategy.data.calendar import build_expiry_table, load_sessions
from options_strategy.data.schemas import (
    ET,
    EXPIRIES_SCHEMA,
    OPTION_QUOTES_SCHEMA,
    RATES_SCHEMA,
    SESSIONS_SCHEMA,
    SETTLEMENTS_SCHEMA,
    UNDERLYING_BARS_SCHEMA,
    validate_schema,
)
from options_strategy.data.synthetic.config import SyntheticWorldConfig
from options_strategy.data.synthetic.heston import UnderlyingPath, simulate
from options_strategy.data.synthetic.microstructure import make_quotes, snap_to_tick
from options_strategy.data.synthetic.surface import (
    expected_total_variance,
    implied_vol,
    validate_no_butterfly,
)
from options_strategy.pricing import black76

_STREAM_MICRO = 1
_STREAM_DEFECT = 2
_STREAM_FLOW = 3

RATE_TENOR_DAYS = (7, 30, 91, 182, 365)

DEFECT_CROSSED = "crossed"
DEFECT_LOCKED = "locked"
DEFECT_STALE = "stale"

SECONDS_PER_YEAR = 365.0 * 86400.0


@dataclass(frozen=True)
class WorldPaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def underlying(self) -> Path:
        return self.root / "underlying_bars.parquet"

    @property
    def quotes_dir(self) -> Path:
        return self.root / "option_quotes"

    @property
    def rates(self) -> Path:
        return self.root / "rates.parquet"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions.parquet"

    @property
    def expiries(self) -> Path:
        return self.root / "expiries.parquet"

    @property
    def settlements(self) -> Path:
        return self.root / "settlements.parquet"

    @property
    def truth_dir(self) -> Path:
        return self.root / "truth"

    @property
    def truth_forwards(self) -> Path:
        return self.truth_dir / "forwards.parquet"

    @property
    def truth_defects(self) -> Path:
        return self.truth_dir / "injected_defects.parquet"

    @property
    def qa_dir(self) -> Path:
        return self.root / "qa"

    def quote_files(self) -> list[Path]:
        return sorted(self.quotes_dir.glob("date=*.parquet"))


def settle_datetime(expiry: dt.date, settlement: str) -> dt.datetime:
    """ET-naive settlement stamp: PM = 16:00 close print, AM = 09:30 opening print."""
    t = dt.time(16, 0) if settlement == "PM" else dt.time(9, 30)
    return dt.datetime.combine(expiry, t)


def _strike_grid(
    spot: float, near_pct: float, span_pct: float, step_near: float, step_far: float
) -> np.ndarray:
    near_lo = np.floor(spot * (1 - near_pct) / step_near) * step_near
    near_hi = np.ceil(spot * (1 + near_pct) / step_near) * step_near
    near = np.arange(near_lo, near_hi + step_near / 2, step_near)
    far_lo = np.floor(spot * (1 - span_pct) / step_far) * step_far
    far_hi = np.ceil(spot * (1 + span_pct) / step_far) * step_far
    below = np.arange(far_lo, near_lo, step_far)
    above = np.arange(np.ceil(near_hi / step_far) * step_far, far_hi + step_far / 2, step_far)
    grid = np.unique(np.concatenate([below, near, above]))
    return grid[grid > 0]


def _visible_expiries(
    expiries: pl.DataFrame, ts: dt.datetime, n_weeklies: int, n_monthlies: int
) -> list[tuple[dt.date, str, str]]:
    out: list[tuple[dt.date, str, str]] = []
    wk = mo = 0
    for expiry, root, settlement in expiries.iter_rows():
        if settle_datetime(expiry, settlement) <= ts:
            continue
        if root == "SPXW" and wk < n_weeklies:
            out.append((expiry, root, settlement))
            wk += 1
        elif root == "SPX" and mo < n_monthlies:
            out.append((expiry, root, settlement))
            mo += 1
        if wk >= n_weeklies and mo >= n_monthlies:
            break
    return out


def generate_world(cfg: SyntheticWorldConfig, out_root: Path | str) -> tuple[WorldPaths, dict]:
    paths = WorldPaths(Path(out_root) / cfg.name)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.quotes_dir.mkdir(exist_ok=True)
    paths.truth_dir.mkdir(exist_ok=True)

    sessions = load_sessions(cfg.start, cfg.end)
    expiries = build_expiry_table(cfg.start, cfg.end, cfg.expiry_rules).sort(
        ["expiry_date", "root"]
    )
    path = simulate(cfg, sessions)

    tau_min = 1.0 / (365.0 * 390.0)
    v_lo = max(float(path.v.min()), 1e-6)
    v_hi = max(float(path.v.max()), cfg.heston.theta)
    theta_lo = float(expected_total_variance(v_lo, tau_min, cfg.heston))
    theta_hi = float(expected_total_variance(v_hi, 1.1, cfg.heston))
    validate_no_butterfly(cfg.surface, max(theta_lo, 1e-12), theta_hi)

    rng_micro = np.random.default_rng(np.random.SeedSequence([cfg.seed, _STREAM_MICRO]))
    rng_defect = np.random.default_rng(np.random.SeedSequence([cfg.seed, _STREAM_DEFECT]))
    rng_flow = np.random.default_rng(np.random.SeedSequence([cfg.seed, _STREAM_FLOW]))

    intraday_sessions: set[dt.date] = set()
    for w_start, w_end in cfg.snapshots.intraday_windows:
        for d in sessions["session"].to_list():
            if w_start <= d <= w_end:
                intraday_sessions.add(d)

    r = cfg.rates.base_rate
    q = cfg.rates.div_yield
    truth_rows: list[dict] = []
    injected_rows: list[dict] = []
    n_quote_rows = 0

    session_dates = [d_.astype(object) for d_ in path.session_dates]
    for i, sess_date in enumerate(session_dates):
        sl = path.session_slice(i)
        is_intraday = sess_date in intraday_sessions
        if is_intraday:
            bar_offsets = range(sl.stop - sl.start)
        elif cfg.snapshots.eod:
            bar_offsets = [sl.stop - sl.start - 1]
        else:
            continue

        cols: dict[str, list[np.ndarray]] = {k: [] for k in OPTION_QUOTES_SCHEMA}
        for off in bar_offsets:
            gi = sl.start + off
            ts_np = path.ts[gi]
            ts_py = ts_np.astype("datetime64[us]").astype(object)
            s_t = float(path.s[gi])
            v_t = float(path.v[gi])
            visible = _visible_expiries(
                expiries, ts_py, cfg.chain.n_weeklies, cfg.chain.n_monthlies
            )
            strikes = _strike_grid(
                s_t,
                cfg.chain.near_band_pct,
                cfg.chain.span_pct,
                cfg.chain.strike_step_near,
                cfg.chain.strike_step_far,
            )
            nk = len(strikes)
            is_eod_bar = off == (sl.stop - sl.start - 1)

            for expiry, root, settlement in visible:
                tau = (settle_datetime(expiry, settlement) - ts_py).total_seconds()
                tau /= SECONDS_PER_YEAR
                fwd = s_t * np.exp((r - q) * tau)
                df = float(np.exp(-r * tau))
                k = np.log(strikes / fwd)
                theta_t = float(expected_total_variance(v_t, tau, cfg.heston))
                iv = implied_vol(k, tau, np.full(nk, theta_t), cfg.surface)
                k_norm = np.abs(k) / np.sqrt(theta_t)
                v_ratio = v_t / cfg.heston.theta

                truth_rows.append(
                    {
                        "ts": ts_py,
                        "root": root,
                        "expiry_date": expiry,
                        "forward": fwd,
                        "df": df,
                        "r": r,
                        "q": q,
                        "v_t": v_t,
                        "theta_t": theta_t,
                    }
                )

                for cp_name, cp_sign_ in (("C", 1), ("P", -1)):
                    mids = black76.price(fwd, strikes, tau, iv, df, cp=cp_sign_)
                    qb = make_quotes(mids, k_norm, v_ratio, cfg.micro, rng_micro)
                    last = np.clip(snap_to_tick(mids, side=-1), qb.bid, qb.ask)
                    vol_lam = (200.0 if is_eod_bar else 3.0) * np.exp(-0.8 * k_norm)
                    volume = rng_flow.poisson(vol_lam).astype(np.int64)
                    oi_vals = _deterministic_oi(root, expiry, cp_name, strikes)

                    cols["ts"].append(np.full(nk, ts_np, dtype="datetime64[us]"))
                    cols["root"].append(np.full(nk, root, dtype="U4"))
                    cols["expiry_date"].append(
                        np.full(nk, np.datetime64(expiry), dtype="datetime64[D]")
                    )
                    cols["am_pm_settle"].append(np.full(nk, settlement, dtype="U2"))
                    cols["strike"].append(strikes)
                    cols["cp"].append(np.full(nk, cp_name, dtype="U1"))
                    cols["bid"].append(qb.bid)
                    cols["ask"].append(qb.ask)
                    cols["bid_size"].append(qb.bid_size)
                    cols["ask_size"].append(qb.ask_size)
                    cols["last"].append(last)
                    cols["volume"].append(volume)
                    cols["open_interest"].append(oi_vals)
                    cols["quote_condition"].append(np.zeros(nk, dtype=np.int32))

        frame = pl.DataFrame(
            {name: np.concatenate(chunks) for name, chunks in cols.items()}
        ).with_columns(
            pl.col("ts").cast(pl.Datetime("us")).dt.replace_time_zone(ET),
            pl.col("expiry_date").cast(pl.Date),
            pl.col("quote_condition").cast(pl.Int32),
        )
        frame, session_injected = _inject_defects(frame, is_intraday, cfg, rng_defect)
        injected_rows.extend(session_injected)
        frame = frame.sort(["ts", "expiry_date", "root", "strike", "cp"])
        validate_schema(frame, OPTION_QUOTES_SCHEMA, "option_quotes")
        frame.write_parquet(paths.quotes_dir / f"date={sess_date.isoformat()}.parquet")
        n_quote_rows += frame.height

    _write_underlying(path, paths)
    validate_schema(sessions, SESSIONS_SCHEMA, "sessions").write_parquet(paths.sessions)
    validate_schema(expiries, EXPIRIES_SCHEMA, "expiries").write_parquet(paths.expiries)
    _write_rates(sessions, cfg, paths)
    _write_settlements(path, expiries, cfg, paths)

    truth_schema = {
        "ts": pl.Datetime("us", ET),
        "root": pl.String(),
        "expiry_date": pl.Date(),
        "forward": pl.Float64(),
        "df": pl.Float64(),
        "r": pl.Float64(),
        "q": pl.Float64(),
        "v_t": pl.Float64(),
        "theta_t": pl.Float64(),
    }
    if truth_rows:
        truth = pl.DataFrame(truth_rows).with_columns(pl.col("ts").dt.replace_time_zone(ET))
    else:  # candles-only worlds (regime studies) emit no chain snapshots
        truth = pl.DataFrame(schema=truth_schema)
    truth.sort(["ts", "expiry_date", "root"]).write_parquet(paths.truth_forwards)
    _write_injected(injected_rows, paths)

    summary = {
        "n_sessions": sessions.height,
        "n_quote_rows": n_quote_rows,
        "n_truth_snapshots": truth.height,
        "n_injected_defects": len(injected_rows),
        "n_expiries": expiries.height,
    }
    manifest = {
        "label": "SYNTHETIC — generated by options_strategy.data.synthetic; not market data",
        "name": cfg.name,
        "config_hash": config_hash(cfg),
        "data_version": cfg.data_version,
        "package_version": __version__,
        "summary": summary,
        "config": json.loads(canonical_json(cfg)),
    }
    paths.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return paths, summary


def _deterministic_oi(root: str, expiry: dt.date, cp: str, strikes: np.ndarray) -> np.ndarray:
    """Stateless pseudo-random open interest per option identity.

    OI is an EOD-only display field never used by strategies (PLAN §14); it just
    needs to be plausible, non-negative, and identical across regenerations
    without consuming RNG stream state (which would couple OI to generation
    order). Classic fract(sin) hash on the identity.
    """
    tenor_code = float(expiry.toordinal() % 1000)
    root_code = 13.0 if root == "SPX" else 29.0
    cp_code = 7.0 if cp == "C" else 3.0
    u = np.abs(np.sin(strikes * 0.129898 + tenor_code * 0.78233 + root_code + cp_code))
    u = (u * 43758.5453) % 1.0
    return (50.0 + u * 4500.0).astype(np.int64)


def _inject_defects(
    frame: pl.DataFrame, is_intraday: bool, cfg: SyntheticWorldConfig, rng: np.random.Generator
) -> tuple[pl.DataFrame, list[dict]]:
    """Inject QA-exercise defects. Stale windows go first and claim their rows;
    crossed/locked then sample only unclaimed rows, keeping the three defect
    sets disjoint so every recorded defect exists verbatim in the written data.
    """
    mp = cfg.micro
    injected: list[dict] = []
    if mp.crossed_rate <= 0 and mp.locked_rate <= 0 and (not is_intraday or mp.stale_rate <= 0):
        return frame, injected

    df = frame.with_row_index("_idx")
    n = df.height
    key_cols = ["ts", "root", "expiry_date", "strike", "cp"]
    claimed = np.zeros(n, dtype=bool)

    def record(rows: pl.DataFrame, defect: str) -> None:
        for row in rows.select(key_cols).iter_rows(named=True):
            injected.append({**row, "defect": defect})

    if is_intraday and mp.stale_rate > 0:
        n_ts_all = df["ts"].n_unique()
        idents = (
            df.group_by(["root", "expiry_date", "strike", "cp"], maintain_order=True)
            .agg(
                pl.len().alias("_n"),
                ((pl.col("bid") + pl.col("ask")) / 2.0).min().alias("_min_mid"),
                pl.col("bid").min().alias("_min_bid"),
            )
            .filter(
                (pl.col("_n") == n_ts_all)
                & (pl.col("_min_mid") >= mp.stale_target_min_mid)
                & (pl.col("_min_bid") > 0)
            )
            .drop(["_n", "_min_mid", "_min_bid"])
            .sort(["expiry_date", "root", "strike", "cp"])
        )
        n_pick = round(idents.height * mp.stale_rate)
        if n_pick:
            pick_idx = np.sort(rng.choice(idents.height, size=n_pick, replace=False))
            ts_sorted = df["ts"].unique().sort()
            n_ts = len(ts_sorted)
            freeze_len = mp.stale_minutes + 5
            for ident in idents[pick_idx.tolist()].iter_rows(named=True):
                if n_ts <= freeze_len + 2:
                    continue
                u = int(rng.integers(1, n_ts - freeze_len - 1))
                t0, t1 = ts_sorted[u], ts_sorted[u + freeze_len - 1]
                sel = (
                    (pl.col("root") == ident["root"])
                    & (pl.col("expiry_date") == ident["expiry_date"])
                    & (pl.col("strike") == ident["strike"])
                    & (pl.col("cp") == ident["cp"])
                )
                src = df.filter(sel & (pl.col("ts") == t0))
                if src.height != 1:
                    continue
                b0, a0 = src["bid"][0], src["ask"][0]
                bs0, as0 = src["bid_size"][0], src["ask_size"][0]
                in_win = sel & (pl.col("ts") >= t0) & (pl.col("ts") <= t1)
                df = df.with_columns(
                    bid=pl.when(in_win).then(pl.lit(b0)).otherwise(pl.col("bid")),
                    ask=pl.when(in_win).then(pl.lit(a0)).otherwise(pl.col("ask")),
                    bid_size=pl.when(in_win).then(pl.lit(bs0)).otherwise(pl.col("bid_size")),
                    ask_size=pl.when(in_win).then(pl.lit(as0)).otherwise(pl.col("ask_size")),
                )
                win_rows = df.filter(in_win)
                claimed[win_rows["_idx"].to_numpy()] = True
                record(win_rows, DEFECT_STALE)

    def sample_unclaimed(n_pick: int) -> np.ndarray:
        pool = np.nonzero(~claimed)[0]
        if n_pick <= 0 or len(pool) == 0:
            return np.empty(0, dtype=np.int64)
        picked = np.sort(rng.choice(pool, size=min(n_pick, len(pool)), replace=False))
        claimed[picked] = True
        return picked

    for rate, defect in ((mp.crossed_rate, DEFECT_CROSSED), (mp.locked_rate, DEFECT_LOCKED)):
        if rate <= 0:
            continue
        picked = sample_unclaimed(round(n * rate))
        if len(picked) == 0:
            continue
        mask = np.zeros(n, dtype=bool)
        mask[picked] = True
        new_bid = pl.col("ask") + 0.05 if defect == DEFECT_CROSSED else pl.col("ask")
        new_size = 10 if defect == DEFECT_CROSSED else 5
        df = df.with_columns(pl.Series("_pick", mask)).with_columns(
            bid=pl.when(pl.col("_pick")).then(new_bid).otherwise(pl.col("bid")),
            bid_size=pl.when(pl.col("_pick"))
            .then(pl.lit(new_size, dtype=pl.Int64))
            .otherwise(pl.col("bid_size")),
        )
        record(df.filter(pl.col("_pick")), defect)
        df = df.drop("_pick")

    return df.drop("_idx"), injected


def _write_underlying(path: UnderlyingPath, paths: WorldPaths) -> None:
    closes = path.s
    opens = np.empty_like(closes)
    for i in range(len(path.session_dates)):
        sl = path.session_slice(i)
        opens[sl.start] = closes[sl.start]
        opens[sl.start + 1 : sl.stop] = closes[sl.start : sl.stop - 1]
    bars = pl.DataFrame(
        {
            "ts": path.ts,
            "open": opens,
            "high": np.maximum(opens, closes),
            "low": np.minimum(opens, closes),
            "close": closes,
        }
    ).with_columns(pl.col("ts").cast(pl.Datetime("us")).dt.replace_time_zone(ET))
    validate_schema(bars, UNDERLYING_BARS_SCHEMA, "underlying_bars")
    bars.write_parquet(paths.underlying)


def _write_rates(sessions: pl.DataFrame, cfg: SyntheticWorldConfig, paths: WorldPaths) -> None:
    dates = sessions["session"].to_list()
    rows = [
        {"date": d, "tenor_days": t, "rate": cfg.rates.base_rate}
        for d in dates
        for t in RATE_TENOR_DAYS
    ]
    df = pl.DataFrame(rows, schema=RATES_SCHEMA, orient="row")
    validate_schema(df, RATES_SCHEMA, "rates").write_parquet(paths.rates)


def _write_settlements(
    path: UnderlyingPath, expiries: pl.DataFrame, cfg: SyntheticWorldConfig, paths: WorldPaths
) -> None:
    by_date = {d.astype(object): i for i, d in enumerate(path.session_dates)}
    rows = []
    for expiry, root, settlement in expiries.iter_rows():
        i = by_date.get(expiry)
        if i is None:
            continue
        sl = path.session_slice(i)
        value = float(path.s[sl.start]) if settlement == "AM" else float(path.s[sl.stop - 1])
        rows.append({"expiry_date": expiry, "root": root, "settlement": settlement, "value": value})
    df = pl.DataFrame(rows, schema=SETTLEMENTS_SCHEMA, orient="row").sort(["expiry_date", "root"])
    validate_schema(df, SETTLEMENTS_SCHEMA, "settlements").write_parquet(paths.settlements)


def _write_injected(injected_rows: list[dict], paths: WorldPaths) -> None:
    schema = {
        "ts": pl.Datetime("us", ET),
        "root": pl.String(),
        "expiry_date": pl.Date(),
        "strike": pl.Float64(),
        "cp": pl.String(),
        "defect": pl.String(),
    }
    if injected_rows:
        df = pl.DataFrame(injected_rows, schema=schema).sort(
            ["ts", "expiry_date", "root", "strike", "cp", "defect"]
        )
    else:
        df = pl.DataFrame(schema=schema)
    df.write_parquet(paths.truth_defects)
