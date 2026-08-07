"""Data QA gate (PLAN §4.2): run before anything touches a dataset.

Layering: row-level sanity flags first (crossed / locked / off-tick / stale);
parity fits, bounds, monotonicity, convexity and calendar checks then run on
the SANE subset only — exactly the subset the fill model is allowed to touch.

For synthetic worlds the gate reconciles against truth tables: every flagged
row must be an injected defect (no unexpected flags), every injected defect
episode must be detected, and parity-extracted forwards must match the
generator's truth. "Clean" is a machine verdict, not an impression.

Flag codes (bitmask): 1 crossed, 2 locked, 4 off-tick, 8 bound violation,
16 stale, 32 parity-outlier snapshot, 64 monotonicity, 128 butterfly,
256 calendar. Bit arithmetic uses floor-div/mod so no reliance on engine
bitwise-operator support.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict

from options_strategy.data.schemas import ET
from options_strategy.data.synthetic.world import SECONDS_PER_YEAR, WorldPaths, settle_datetime

FLAG_CROSSED = 1
FLAG_LOCKED = 2
FLAG_TICK = 4
FLAG_BOUND = 8
FLAG_STALE = 16
FLAG_PARITY = 32
FLAG_MONO = 64
FLAG_FLY = 128
FLAG_CALENDAR = 256

_IDENT = ["root", "expiry_date", "strike", "cp"]
_KEY = ["ts", *_IDENT]

_FLAGS_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", ET),
    "root": pl.String(),
    "expiry_date": pl.Date(),
    "strike": pl.Float64(),
    "cp": pl.String(),
    "flags": pl.Int32(),
}

_FORWARDS_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", ET),
    "root": pl.String(),
    "expiry_date": pl.Date(),
    "tau_years": pl.Float64(),
    "n_strikes": pl.Int64(),
    "df_hat": pl.Float64(),
    "forward_hat": pl.Float64(),
    "rmse": pl.Float64(),
    "parity_ok": pl.Boolean(),
}


class QAConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    parity_rmse_tol: float = 0.25
    parity_min_strikes: int = 8
    stale_minutes: int = 45
    stale_min_premium: float = 0.50
    mono_tol_half_spreads: float = 1.0
    fly_tol_half_spreads: float = 1.0
    calendar_tol_half_spreads: float = 1.5
    bound_slack: float = 0.01
    forward_truth_rel_tol: float = 2e-4
    df_truth_abs_tol: float = 5e-4
    # DF is unidentifiable from parity slopes minutes before settlement (the
    # regression can't resolve 1-r*tau at tau ~ 1e-6), so the DF-vs-truth gate
    # applies only to fits with at least this much tenor. Forwards are gated at
    # ALL tenors. See ASSUMPTIONS.md.
    df_min_tenor_years: float = 1.0 / 365.0


@dataclass(frozen=True)
class QAResult:
    clean: bool
    summary: dict
    report_path: Path
    flags_path: Path
    forwards_path: Path


def _has_bit(expr: pl.Expr, bit: int) -> pl.Expr:
    return (expr // bit) % 2 == 1


def _has_any_bit(expr: pl.Expr, bits: tuple[int, ...]) -> pl.Expr:
    cond = _has_bit(expr, bits[0])
    for b in bits[1:]:
        cond = cond | _has_bit(expr, b)
    return cond


def _tick_ok(price: pl.Expr) -> pl.Expr:
    tick = pl.when(price < 3.0).then(0.05).otherwise(0.10)
    return ((price / tick) - (price / tick).round(0)).abs() * tick < 1e-6


def _sanity_flags(frame: pl.DataFrame, cfg: QAConfig, bar_minutes: int) -> pl.DataFrame:
    df = frame.with_columns(
        mid=(pl.col("bid") + pl.col("ask")) / 2.0,
        half=(pl.col("ask") - pl.col("bid")) / 2.0,
    )
    crossed = pl.when(pl.col("bid") > pl.col("ask") + 1e-9).then(FLAG_CROSSED).otherwise(0)
    locked = pl.when((pl.col("bid") - pl.col("ask")).abs() < 1e-12).then(FLAG_LOCKED).otherwise(0)
    off_tick = (
        pl.when(~(_tick_ok(pl.col("bid")) & _tick_ok(pl.col("ask")))).then(FLAG_TICK).otherwise(0)
    )
    df = df.with_columns(flags=(crossed + locked + off_tick).cast(pl.Int32))

    if df["ts"].n_unique() > 1:
        stale_bars = max(int(np.ceil(cfg.stale_minutes / bar_minutes)), 1)
        df = df.sort([*_IDENT, "ts"])
        changed = (
            (pl.col("bid").diff().over(_IDENT).fill_null(1.0).abs() > 1e-12)
            | (pl.col("ask").diff().over(_IDENT).fill_null(1.0).abs() > 1e-12)
        ).cast(pl.Int32)
        df = df.with_columns(run_id=changed.cum_sum().over(_IDENT))
        df = df.with_columns(run_pos=pl.int_range(pl.len()).over([*_IDENT, "run_id"]))
        stale = (
            pl.when((pl.col("run_pos") >= stale_bars) & (pl.col("mid") >= cfg.stale_min_premium))
            .then(FLAG_STALE)
            .otherwise(0)
        )
        df = df.with_columns(flags=(pl.col("flags") + stale).cast(pl.Int32)).drop(
            ["run_id", "run_pos"]
        )
    return df


def _parity_fit(sane: pl.DataFrame, cfg: QAConfig) -> tuple[list[dict], dict[tuple, tuple]]:
    """OLS of (C - P) on K per (ts, root, expiry): slope=-DF, intercept=DF*F."""
    fits: list[dict] = []
    lookup: dict[tuple, tuple] = {}
    calls = sane.filter(pl.col("cp") == "C").select(
        "ts", "root", "expiry_date", "am_pm_settle", "strike", "mid", "half"
    )
    puts = sane.filter(pl.col("cp") == "P").select(
        "ts", "root", "expiry_date", "strike", "mid", "half"
    )
    joined = calls.join(puts, on=["ts", "root", "expiry_date", "strike"], suffix="_p").sort(
        ["ts", "expiry_date", "root", "strike"]
    )
    for (ts, root, expiry), grp in joined.group_by(
        ["ts", "root", "expiry_date"], maintain_order=True
    ):
        if grp.height < cfg.parity_min_strikes:
            continue
        settle = settle_datetime(expiry, grp["am_pm_settle"][0])
        tau_years = (settle - ts.replace(tzinfo=None)).total_seconds() / SECONDS_PER_YEAR
        k = grp["strike"].to_numpy()
        y = (grp["mid"] - grp["mid_p"]).to_numpy()
        a_mat = np.column_stack([np.ones_like(k), k])
        coef, _, _, _ = np.linalg.lstsq(a_mat, y, rcond=None)
        resid = y - a_mat @ coef
        rmse = float(np.sqrt(np.mean(resid**2)))
        df_hat = float(-coef[1])
        f_hat = float(coef[0] / df_hat) if df_hat > 1e-9 else float("nan")
        ok = bool(rmse <= cfg.parity_rmse_tol and 0.3 < df_hat <= 1.02 and np.isfinite(f_hat))
        fits.append(
            {
                "ts": ts,
                "root": root,
                "expiry_date": expiry,
                "tau_years": tau_years,
                "n_strikes": grp.height,
                "df_hat": df_hat,
                "forward_hat": f_hat,
                "rmse": rmse,
                "parity_ok": ok,
            }
        )
        lookup[(ts, root, expiry)] = (df_hat, f_hat, ok)
    return fits, lookup


def _key_row(ts, root, expiry, strike, cp, flag: int) -> dict:
    return {
        "ts": ts,
        "root": root,
        "expiry_date": expiry,
        "strike": float(strike),
        "cp": cp,
        "flags": flag,
    }


def _structure_flags(
    sane: pl.DataFrame, lookup: dict[tuple, tuple], cfg: QAConfig
) -> tuple[list[dict], dict[str, int]]:
    """Bounds / monotonicity / butterfly on the sane subset."""
    counts = {"bound": 0, "mono": 0, "fly": 0}
    flag_rows: list[dict] = []

    for (ts, root, expiry, cp), grp in sane.group_by(
        ["ts", "root", "expiry_date", "cp"], maintain_order=True
    ):
        g = grp.sort("strike")
        k = g["strike"].to_numpy()
        mid = g["mid"].to_numpy()
        half = g["half"].to_numpy()
        bid = g["bid"].to_numpy()
        ask = g["ask"].to_numpy()
        n = len(k)

        fit = lookup.get((ts, root, expiry))
        if fit is not None and fit[2]:
            df_hat, f_hat = fit[0], fit[1]
            if cp == "C":
                upper = df_hat * f_hat
                intrinsic = df_hat * np.maximum(f_hat - k, 0.0)
            else:
                upper = df_hat * k
                intrinsic = df_hat * np.maximum(k - f_hat, 0.0)
            bad = (bid > upper + cfg.bound_slack) | (ask < intrinsic - cfg.bound_slack)
            for i in np.nonzero(bad)[0]:
                counts["bound"] += 1
                flag_rows.append(_key_row(ts, root, expiry, k[i], cp, FLAG_BOUND))

        if n >= 2:
            dmid = np.diff(mid)
            tol = cfg.mono_tol_half_spreads * (half[:-1] + half[1:])
            bad_step = dmid > tol if cp == "C" else -dmid > tol
            for i in np.nonzero(bad_step)[0]:
                counts["mono"] += 1
                flag_rows.append(_key_row(ts, root, expiry, k[i + 1], cp, FLAG_MONO))

        if n >= 3:
            span = k[2:] - k[:-2]
            w1 = (k[2:] - k[1:-1]) / span
            w2 = (k[1:-1] - k[:-2]) / span
            fly = w1 * mid[:-2] + w2 * mid[2:] - mid[1:-1]
            tol = cfg.fly_tol_half_spreads * (w1 * half[:-2] + w2 * half[2:] + half[1:-1])
            for i in np.nonzero(fly < -tol)[0]:
                counts["fly"] += 1
                flag_rows.append(_key_row(ts, root, expiry, k[i + 1], cp, FLAG_FLY))

    return flag_rows, counts


def _calendar_check(
    sane: pl.DataFrame, lookup: dict[tuple, tuple], cfg: QAConfig
) -> tuple[list[dict], int]:
    """ATM straddle must be non-decreasing in time-to-settle per snapshot.

    (The k-grid total-variance version of this check arrives with the P1 IV
    solver; this price-space version needs no vol solving.)
    """
    viol_rows: list[dict] = []
    n_viol = 0
    per_ts: dict[object, list[tuple]] = {}
    calls = sane.filter(pl.col("cp") == "C").select(
        "ts", "root", "expiry_date", "strike", "mid", "half"
    )
    puts = sane.filter(pl.col("cp") == "P").select(
        "ts", "root", "expiry_date", "strike", "mid", "half"
    )
    joined = calls.join(puts, on=["ts", "root", "expiry_date", "strike"], suffix="_p")
    for (ts, root, expiry), grp in joined.group_by(
        ["ts", "root", "expiry_date"], maintain_order=True
    ):
        fit = lookup.get((ts, root, expiry))
        if fit is None or not fit[2]:
            continue
        f_hat = fit[1]
        idx = int(np.argmin(np.abs(grp["strike"].to_numpy() - f_hat)))
        row = grp.row(idx, named=True)
        settle = settle_datetime(expiry, "PM" if root == "SPXW" else "AM")
        per_ts.setdefault(ts, []).append(
            (
                settle,
                root,
                expiry,
                row["strike"],
                row["mid"] + row["mid_p"],
                row["half"] + row["half_p"],
            )
        )
    for ts, entries in per_ts.items():
        entries.sort()
        for (_s1, r1, e1, k1, st1, t1), (_s2, r2, e2, k2, st2, t2) in pairwise(entries):
            if st2 < st1 - cfg.calendar_tol_half_spreads * (t1 + t2):
                n_viol += 1
                for root, expiry, strike in ((r1, e1, k1), (r2, e2, k2)):
                    for cp in ("C", "P"):
                        viol_rows.append(_key_row(ts, root, expiry, strike, cp, FLAG_CALENDAR))
    return viol_rows, n_viol


def run_qa(world_root: Path | str, cfg: QAConfig | None = None) -> QAResult:
    cfg = cfg or QAConfig()
    paths = WorldPaths(Path(world_root))
    if not paths.manifest.exists():
        raise FileNotFoundError(f"no manifest at {paths.manifest} — not a dataset root")
    manifest = json.loads(paths.manifest.read_text())
    sessions = pl.read_parquet(paths.sessions)

    flag_frames: list[pl.DataFrame] = []
    parity_rows: list[dict] = []
    coverage_rows: list[dict] = []
    structure_counts = {"bound": 0, "mono": 0, "fly": 0}
    n_calendar_viol = 0
    n_parity_bad = 0
    n_rows_total = 0

    for f in paths.quote_files():
        frame = pl.read_parquet(f)
        n_rows_total += frame.height
        ts_unique = frame["ts"].unique().sort()
        bar_minutes = 1
        if len(ts_unique) > 1:
            bar_minutes = max(int((ts_unique[1] - ts_unique[0]).total_seconds() // 60), 1)

        flagged = _sanity_flags(frame, cfg, bar_minutes)
        sane = flagged.filter((pl.col("flags") == 0) & (pl.col("bid") > 0))

        fits, lookup = _parity_fit(sane, cfg)
        parity_rows.extend(fits)
        n_parity_bad += sum(1 for r in fits if not r["parity_ok"])

        struct_rows, counts = _structure_flags(sane, lookup, cfg)
        for key in structure_counts:
            structure_counts[key] += counts[key]
        cal_rows, cal_viol = _calendar_check(sane, lookup, cfg)
        n_calendar_viol += cal_viol

        parts = [flagged.filter(pl.col("flags") != 0).select([*_KEY, "flags"])]
        extra_rows = struct_rows + cal_rows
        if extra_rows:
            parts.append(pl.DataFrame(extra_rows, schema=_FLAGS_SCHEMA))
        session_all = (
            pl.concat(parts)
            .group_by(_KEY)
            .agg(pl.col("flags").unique().sum().cast(pl.Int32).alias("flags"))
        )
        flag_frames.append(session_all)

        session_date = dt.date.fromisoformat(f.stem.removeprefix("date="))
        srow = sessions.filter(pl.col("session") == session_date)
        expected_bars = None
        if len(ts_unique) > 1 and srow.height == 1:
            open_et, close_et = srow["open_et"][0], srow["close_et"][0]
            expected_bars = int((close_et - open_et).total_seconds() // (60 * bar_minutes))
        coverage_rows.append(
            {
                "session": session_date.isoformat(),
                "n_rows": frame.height,
                "n_snapshots": len(ts_unique),
                "expected_bars": expected_bars,
                "missing_bars": (expected_bars - len(ts_unique)) if expected_bars else 0,
                "n_expiries": frame.select("expiry_date", "root").unique().height,
                "min_strikes_side": int(
                    frame.group_by("ts", "expiry_date", "root", "cp")
                    .agg(pl.len())
                    .select(pl.col("len").min())
                    .item()
                ),
            }
        )

    flags_df = (
        pl.concat(flag_frames).sort(_KEY) if flag_frames else pl.DataFrame(schema=_FLAGS_SCHEMA)
    )
    forwards_df = (
        pl.DataFrame(parity_rows, schema_overrides=_FORWARDS_SCHEMA).sort(
            ["ts", "expiry_date", "root"]
        )
        if parity_rows
        else pl.DataFrame(schema=_FORWARDS_SCHEMA)
    )

    truth_stats, unexpected, missed = _reconcile_with_truth(paths, flags_df, forwards_df, cfg)

    coverage_df = pl.DataFrame(coverage_rows)
    missing_bars_total = int(coverage_df["missing_bars"].fill_null(0).sum()) if coverage_rows else 0
    sessions_without_file = sessions.height - len(coverage_rows)

    truth_fwd_ok = (
        truth_stats.get("forward_rel_err_max", 0.0) <= cfg.forward_truth_rel_tol
        and truth_stats.get("df_abs_err_max", 0.0) <= cfg.df_truth_abs_tol
    )
    clean = bool(
        unexpected["sanity_rows"] == 0
        and unexpected["structure_rows"] == 0
        and unexpected["parity_bad"] == 0
        and missed["crossed_locked_rows"] == 0
        and missed["stale_episodes"] == 0
        and missing_bars_total == 0
        and sessions_without_file == 0
        and truth_fwd_ok
    )

    summary = {
        "clean": clean,
        "n_rows": n_rows_total,
        "n_sessions": len(coverage_rows),
        "sessions_without_file": sessions_without_file,
        "missing_bars_total": missing_bars_total,
        "n_flagged_rows": int(flags_df.height),
        "n_parity_fits": forwards_df.height,
        "n_parity_bad": n_parity_bad,
        "structure_violations": structure_counts,
        "calendar_violations": n_calendar_viol,
        "unexpected": unexpected,
        "missed_injected": missed,
        "truth": truth_stats,
        "data_version": manifest.get("data_version", "unknown"),
    }

    paths.qa_dir.mkdir(exist_ok=True)
    flags_path = paths.qa_dir / "quality_flags.parquet"
    forwards_path = paths.qa_dir / "forwards_extracted.parquet"
    report_path = paths.qa_dir / "report.md"
    flags_df.write_parquet(flags_path)
    forwards_df.write_parquet(forwards_path)
    report_path.write_text(_render_report(manifest, summary, coverage_df))
    (paths.qa_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    return QAResult(
        clean=clean,
        summary=summary,
        report_path=report_path,
        flags_path=flags_path,
        forwards_path=forwards_path,
    )


def _reconcile_with_truth(
    paths: WorldPaths, flags_df: pl.DataFrame, forwards_df: pl.DataFrame, cfg: QAConfig
) -> tuple[dict, dict, dict]:
    """Attribution semantics: with injected-defect truth available, sanity
    flags must match injected rows exactly; structure/parity violations are
    expected only inside snapshots that contain injected rows (an undetectable
    freeze prefix still corrupts its snapshot's fits — that is attributable,
    not unexpected); forwards-vs-truth excludes those snapshots. Without truth
    tables (real data), everything counts — full strictness.
    """
    truth_stats: dict = {}
    unexpected = {"sanity_rows": 0, "structure_rows": 0, "parity_bad": 0}
    missed = {"crossed_locked_rows": 0, "stale_episodes": 0}
    group_keys = ["ts", "root", "expiry_date"]

    sanity_flagged = flags_df.filter(
        _has_any_bit(pl.col("flags"), (FLAG_CROSSED, FLAG_LOCKED, FLAG_TICK, FLAG_STALE))
    )
    bmf_flagged = flags_df.filter(_has_any_bit(pl.col("flags"), (FLAG_BOUND, FLAG_MONO, FLAG_FLY)))
    cal_flagged = flags_df.filter(_has_bit(pl.col("flags"), FLAG_CALENDAR))
    parity_bad_df = forwards_df.filter(~pl.col("parity_ok"))

    injected = pl.read_parquet(paths.truth_defects) if paths.truth_defects.exists() else None
    inj_groups: pl.DataFrame | None = None
    if injected is not None and injected.height:
        inj_keys = injected.select(_KEY).unique()
        inj_groups = injected.select(group_keys).unique()
        inj_ts = injected.select("ts").unique()
        unexpected["sanity_rows"] = sanity_flagged.join(inj_keys, on=_KEY, how="anti").height
        unexpected["structure_rows"] = (
            bmf_flagged.join(inj_groups, on=group_keys, how="anti").height
            + cal_flagged.join(inj_ts, on=["ts"], how="anti").height
        )
        unexpected["parity_bad"] = parity_bad_df.join(inj_groups, on=group_keys, how="anti").height
        cl = injected.filter(pl.col("defect").is_in(["crossed", "locked"]))
        detected_cl = flags_df.filter(
            _has_any_bit(pl.col("flags"), (FLAG_CROSSED, FLAG_LOCKED, FLAG_TICK))
        )
        missed["crossed_locked_rows"] = cl.join(detected_cl, on=_KEY, how="anti").height
        stale_inj = injected.filter(pl.col("defect") == "stale")
        if stale_inj.height:
            episodes = stale_inj.group_by(["root", "expiry_date", "strike", "cp"]).agg(
                pl.col("ts").min().alias("t0"), pl.col("ts").max().alias("t1")
            )
            stale_hits = flags_df.filter(_has_bit(pl.col("flags"), FLAG_STALE))
            n_missed = 0
            for row in episodes.iter_rows(named=True):
                hit = stale_hits.filter(
                    (pl.col("root") == row["root"])
                    & (pl.col("expiry_date") == row["expiry_date"])
                    & (pl.col("strike") == row["strike"])
                    & (pl.col("cp") == row["cp"])
                    & (pl.col("ts") >= row["t0"])
                    & (pl.col("ts") <= row["t1"])
                )
                if hit.height == 0:
                    n_missed += 1
            missed["stale_episodes"] = n_missed
    else:
        unexpected["sanity_rows"] = sanity_flagged.height
        unexpected["structure_rows"] = bmf_flagged.height + cal_flagged.height
        unexpected["parity_bad"] = parity_bad_df.height

    if paths.truth_forwards.exists() and forwards_df.height:
        truth = pl.read_parquet(paths.truth_forwards)
        joined = forwards_df.join(truth, on=group_keys, how="inner")
        if inj_groups is not None:
            joined = joined.join(inj_groups, on=group_keys, how="anti")
        if joined.height:
            rel = ((joined["forward_hat"] - joined["forward"]).abs() / joined["forward"]).to_numpy()
            dferr_all = (joined["df_hat"] - joined["df"]).abs().to_numpy()
            # DF gate applies only where the tenor makes DF identifiable:
            gated = joined.filter(pl.col("tau_years") >= cfg.df_min_tenor_years)
            dferr_gated = (gated["df_hat"] - gated["df"]).abs().to_numpy()
            truth_stats = {
                "n_compared": joined.height,
                "forward_rel_err_max": float(rel.max()),
                "forward_rel_err_p99": float(np.quantile(rel, 0.99)),
                "df_abs_err_max": float(dferr_gated.max()) if len(dferr_gated) else 0.0,
                "df_abs_err_max_all_tenors": float(dferr_all.max()),
                "n_df_gated": gated.height,
            }
    return truth_stats, unexpected, missed


def _md_table(df: pl.DataFrame) -> str:
    if not df.height:
        return "_empty_"
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.iter_rows():
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def _render_report(manifest: dict, summary: dict, coverage: pl.DataFrame) -> str:
    sv = summary["structure_violations"]
    t = summary.get("truth") or {}
    lines = [
        "# Data QA report",
        "",
        f"**Dataset label:** {manifest.get('label', 'UNKNOWN')}",
        f"**Dataset:** `{manifest.get('name')}` | data_version `{summary['data_version']}`",
        "",
        f"## Verdict: {'CLEAN' if summary['clean'] else 'NOT CLEAN'}",
        "",
        "| check | value |",
        "|---|---|",
        f"| rows | {summary['n_rows']:,} |",
        f"| sessions covered | {summary['n_sessions']} "
        f"(missing files: {summary['sessions_without_file']}) |",
        f"| missing intraday bars | {summary['missing_bars_total']} |",
        f"| flagged rows | {summary['n_flagged_rows']:,} |",
        f"| unexpected sanity flags | {summary['unexpected']['sanity_rows']} |",
        f"| unexpected structure violations | {summary['unexpected']['structure_rows']} |",
        f"| unexpected bad parity fits | {summary['unexpected']['parity_bad']} |",
        f"| missed injected crossed/locked | {summary['missed_injected']['crossed_locked_rows']} |",
        f"| missed injected stale episodes | {summary['missed_injected']['stale_episodes']} |",
        f"| parity fits (raw bad) | {summary['n_parity_fits']} ({summary['n_parity_bad']}) |",
        f"| bound violations (raw) | {sv['bound']} |",
        f"| monotonicity violations (raw) | {sv['mono']} |",
        f"| butterfly violations (raw) | {sv['fly']} |",
        f"| calendar violations (raw) | {summary['calendar_violations']} |",
    ]
    if t:
        lines += [
            f"| forwards vs truth (n) | {t['n_compared']:,} |",
            f"| forward rel err max | {t['forward_rel_err_max']:.2e} |",
            f"| DF abs err max (tenor >= gate, n={t['n_df_gated']}) | {t['df_abs_err_max']:.2e} |",
            f"| DF abs err max (all tenors, ungated info) | {t['df_abs_err_max_all_tenors']:.2e} |",
        ]
    lines += ["", "## Coverage by session", "", _md_table(coverage), ""]
    return "\n".join(lines)
