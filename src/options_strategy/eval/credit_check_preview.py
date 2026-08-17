"""Credit-check PREVIEW driver: 2 of 6 regimes, EOD basis (ThetaData free tier).

Runs eval/credit_check.py (dual credit/debit reading + ATM reference, PLAN
§1.6 2026-08-16 amendment) over the theta EOD preview world for the entry
Fridays of the two free-tier windows (vix-spike-aug-2024, live-window-2026).
Band edges come from the committed candle-study artifact: the (b) table for
the 7-day front, the 14-day variant table for front_dte=14.

REAL vendor data, but a PREVIEW: closing-NBBO EOD marks (not the spec's
15:45 ET snapshot), ^GSPC proxy spot, and only 2 of the 6 regimes. The
report labels all of this. Remaining regimes arrive with the paid month
(reports/theta_pull_plan.md).

Usage:  python -m options_strategy.eval.credit_check_preview
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy.eval.credit_check import run_credit_check
from options_strategy.pricing.forwards import fit_parity

WORLD_ROOT = Path("data/raw/theta/eod_preview/world")
STUDY_JSON = Path("reports/candle_study.json")
REPORT_MD = Path("reports/credit_check_preview.md")

PREVIEW_WINDOWS = {
    "vix-spike-aug-2024": (dt.date(2024, 7, 26), dt.date(2024, 8, 23)),
    "live-window-2026": (dt.date(2026, 4, 2), dt.date(2026, 7, 31)),
}
Q_LABELS = {0.85: "q85", 0.90: "q90", 0.95: "q95"}
FRONT_WINDOWS = {"7d": (5, 9), "14d": (12, 16)}
MIN_PARITY_STRIKES = 8


def parity_fits(
    chain: pl.DataFrame, session: dt.date, min_strikes: int = MIN_PARITY_STRIKES
) -> tuple[dict[dt.date, tuple[float, float, float]], dict[str, float]]:
    """Per-expiry (forward, df, tau) from put-call parity on double-live mids.

    Returns the fits plus rmse diagnostics (reported, never silently
    thresholded — degenerate fits only are dropped).
    """
    live = chain.filter((pl.col("bid") > 0) & (pl.col("ask") >= pl.col("bid")))
    mids = live.with_columns(((pl.col("bid") + pl.col("ask")) / 2.0).alias("mid"))
    fits: dict[dt.date, tuple[float, float, float]] = {}
    rmses: list[float] = []
    for (expiry,), grp in mids.group_by(["expiry_date"], maintain_order=True):
        both = (
            grp.pivot(on="cp", index="strike", values="mid", aggregate_function="mean")
            .drop_nulls()
            .sort("strike")
        )
        if both.height < min_strikes or "C" not in both.columns or "P" not in both.columns:
            continue
        fit = fit_parity(
            both["strike"].to_numpy(), both["C"].to_numpy(), both["P"].to_numpy()
        )
        if not (np.isfinite(fit.forward) and fit.df > 0):
            continue
        tau = (expiry - session).days / 365.0
        if tau <= 0:
            continue
        fits[expiry] = (fit.forward, fit.df, tau)
        rmses.append(fit.rmse)
    diag = {
        "n_expiries_fit": float(len(fits)),
        "rmse_median": float(np.median(rmses)) if rmses else float("nan"),
        "rmse_max": float(np.max(rmses)) if rmses else float("nan"),
    }
    return fits, diag


def band_edges_from_study(study: dict) -> dict[str, dict[str, tuple[float, float]]]:
    """{variant: {label: (put_edge_ret, call_edge_ret)}} from the study artifact."""
    out: dict[str, dict[str, tuple[float, float]]] = {"7d": {}, "14d": {}}
    for row in study["b_coverage"]:
        if row["q"] in Q_LABELS:
            out["7d"][Q_LABELS[row["q"]]] = (row["put_edge_ret"], row["call_edge_ret"])
    for row in study["e_coverage_14d"]:
        if row["q"] in Q_LABELS:
            out["14d"][Q_LABELS[row["q"]]] = (row["put_edge_ret"], row["call_edge_ret"])
    return out


def entry_dates_from_study(study: dict) -> list[dict]:
    """Preview-window entry Fridays from the purchase-spec table (window,
    entry date, EMA state)."""
    rows = []
    for r in study["f_purchase_spec"]:
        if r["window"] not in PREVIEW_WINDOWS:
            continue
        rows.append(
            {
                "window": r["window"],
                "entry_date": dt.date.fromisoformat(r["entry_friday"]),
                "ema_state": r["ema_state"],
            }
        )
    return rows


def run_one_entry(
    chain: pl.DataFrame,
    spot: float,
    session: dt.date,
    edges: dict[str, dict[str, tuple[float, float]]],
) -> pl.DataFrame:
    frames = []
    fits, diag = parity_fits(chain, session)
    for variant, front_window in FRONT_WINDOWS.items():
        df = run_credit_check(
            chain, spot, fits, session, edges[variant], front_dte_window=front_window
        )
        if df.height:
            frames.append(df.with_columns(pl.lit(variant).alias("front_variant")))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames).with_columns(
        pl.lit(diag["rmse_median"]).alias("parity_rmse_median"),
        pl.lit(diag["rmse_max"]).alias("parity_rmse_max"),
        pl.lit(spot).alias("spot"),
    )


def load_spot_by_session(world_root: Path) -> dict[dt.date, float]:
    bars = pl.read_parquet(world_root / "underlying_bars.parquet")
    return {
        ts.date(): c
        for ts, c in zip(bars["ts"].to_list(), bars["close"].to_list(), strict=True)
    }


def run_preview(
    world_root: Path = WORLD_ROOT, study_json: Path = STUDY_JSON
) -> tuple[pl.DataFrame, dict]:
    study = json.loads(study_json.read_text())
    edges = band_edges_from_study(study)
    entries = entry_dates_from_study(study)
    spot_by_session = load_spot_by_session(world_root)
    manifest = json.loads((world_root / "manifest.json").read_text())

    frames, skipped = [], []
    for e in entries:
        qfile = world_root / "option_quotes" / f"date={e['entry_date']}.parquet"
        if not qfile.exists() or e["entry_date"] not in spot_by_session:
            skipped.append(str(e["entry_date"]))
            continue
        chain = pl.read_parquet(qfile)
        df = run_one_entry(chain, spot_by_session[e["entry_date"]], e["entry_date"], edges)
        if df.is_empty():
            skipped.append(str(e["entry_date"]))
            continue
        frames.append(
            df.with_columns(
                pl.lit(e["window"]).alias("window"), pl.lit(e["ema_state"]).alias("ema_state")
            )
        )
    if not frames:
        raise RuntimeError(f"no entry date produced structures; skipped={skipped}")
    all_rows = pl.concat(frames)
    meta = {
        "data_version": manifest["data_version"],
        "n_entries_priced": all_rows["session"].n_unique(),
        "n_entries_skipped": len(skipped),
        "skipped": skipped,
        "n_structures": all_rows.height,
    }
    return all_rows, meta


def _agg_table(rows: pl.DataFrame) -> pl.DataFrame:
    return (
        rows.group_by(["front_variant", "label", "wing_offset"], maintain_order=True)
        .agg(
            pl.len().alias("n"),
            (pl.col("net_premium_pct_risk") > 0).mean().alias("frac_credit"),
            pl.col("net_premium_pct_risk").median().alias("med_net_prem_pct_risk"),
            pl.col("max_gain_pct_risk").median().alias("med_max_gain_pct_risk"),
            pl.col("thirty_pct_achievable").mean().alias("frac_30pct_ok"),
        )
        .sort(["front_variant", "label", "wing_offset"])
    )


def write_report(rows: pl.DataFrame, meta: dict, out_md: Path = REPORT_MD) -> None:
    def fmt(t: pl.DataFrame) -> str:
        hdr = "| " + " | ".join(t.columns) + " |"
        sep = "|" + "---|" * len(t.columns)
        body = [
            "| "
            + " | ".join(
                f"{v:.3f}" if isinstance(v, float) else str(v) for v in r
            )
            + " |"
            for r in t.rows()
        ]
        return "\n".join([hdr, sep, *body])

    per_window = [
        f"### {w}\n\n{fmt(_agg_table(rows.filter(pl.col('window') == w)))}"
        for w in rows["window"].unique().sort().to_list()
    ]
    q90 = rows.filter(
        (pl.col("label") == "q90")
        & (pl.col("wing_offset") == 25.0)
        & (pl.col("front_variant") == "7d")
    ).select(
        "session", "window", "ema_state", "short_put", "short_call",
        "net_premium", "net_premium_pct_risk", "max_gain_pct_risk",
        "thirty_pct_achievable", "parity_rmse_median",
    ).sort("session")

    out_md.write_text(
        "# Credit check PREVIEW — REAL DATA (ThetaData free tier), "
        "**2 of 6 regimes, EOD basis**\n\n"
        "Closing-NBBO EOD marks, NOT the spec's 15:45 ET snapshot; ^GSPC proxy\n"
        "spot; band edges from reports/candle_study.md (b) / 14-day tables.\n"
        "Dual reading per PLAN §1.6 2026-08-16 amendment: `net_premium_pct_risk`\n"
        "is the signed credit reading (positive = credit); `max_gain_pct_risk` is\n"
        "the debit-tolerant return-on-risk reading at front expiry within the\n"
        "band; `frac_30pct_ok` scores the author's '+30% of R' claim against the\n"
        "latter. ATM reference rows (`atm_ref`) measure the 'big credit only if\n"
        "ATM/ITM' line. tau = calendar days / 365 (AM/PM settle fraction\n"
        "ignored at EOD granularity). Not investment advice.\n\n"
        f"- data_version: `{meta['data_version']}`\n"
        f"- entry Fridays priced: {meta['n_entries_priced']}"
        f" (skipped: {meta['n_entries_skipped']} {meta['skipped']})\n"
        f"- structures priced: {meta['n_structures']}\n\n"
        "## Aggregates by window\n\n" + "\n\n".join(per_window) + "\n\n"
        "## Per-entry detail (q90, wing offset 25, 7d front)\n\n" + fmt(q90) + "\n\n"
        "---\n\nRemaining 4 regimes (calm-2017, volmageddon-2018, covid-2020,\n"
        "bear-2022) require the paid STANDARD month: reports/theta_pull_plan.md.\n"
    )


def main() -> None:
    import hashlib

    from options_strategy import ledger

    rows, meta = run_preview()
    write_report(rows, meta)
    cfg = json.dumps(
        {
            "eval": "credit_check_preview",
            "windows": {k: [str(a), str(b)] for k, (a, b) in PREVIEW_WINDOWS.items()},
            "q_labels": sorted(Q_LABELS.values()),
            "front_windows": FRONT_WINDOWS,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    agg = _agg_table(rows)
    q90_7d_25 = agg.filter(
        (pl.col("label") == "q90")
        & (pl.col("wing_offset") == 25.0)
        & (pl.col("front_variant") == "7d")
    )
    ledger.append(
        [
            ledger.LedgerRow(
                kind="credit_check_preview",
                config_hash=hashlib.sha256(cfg.encode("ascii")).hexdigest(),
                git_sha=ledger.current_git_sha(),
                data_version=meta["data_version"],
                seed=0,
                metrics={
                    "n_entries_priced": meta["n_entries_priced"],
                    "n_structures": meta["n_structures"],
                    "frac_credit_q90_7d_off25": float(q90_7d_25["frac_credit"][0])
                    if q90_7d_25.height
                    else None,
                    "frac_30pct_ok_q90_7d_off25": float(q90_7d_25["frac_30pct_ok"][0])
                    if q90_7d_25.height
                    else None,
                },
                artifacts=[str(REPORT_MD)],
            )
        ]
    )
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
