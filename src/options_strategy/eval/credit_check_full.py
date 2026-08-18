"""FULL six-regime credit check on the REAL at_time slice (15:45 ET basis).

Runs eval/credit_check.py over all 51 spec entry dates from the paid-tier
slice world (data/raw/thetadata/credit_check_slice/world), at the spec's
PRIMARY 15:45 ET snapshot: dual credit/debit reading, ATM reference, both
front variants (7d, 14d), and the exit_mode dimension (hold_to_expiry vs
exit_at_7dte, 14d fronts only — 2026-08-18 amendment).

Sensitivity cut (2026-08-18 amendment): every aggregate is reported twice —
all entry dates, and excluding dates whose median parity RMSE > 1.0 pt.

Emits reports/credit_check.md with an explicit VERDICT section including the
CONTINUE/PAUSE gate: the author-consistent corner (14d fronts, q90/q95/
atm_ref, offsets 0-50, either exit mode) must achieve +30%-of-risk on
>= 20% of entry dates in at least 2 of the 4 NEW regimes (calm-2017,
volmageddon-2018, covid-2020, bear-2022); achieving < 20% in 3+ of them
pauses the pipeline for the user.

Usage:  python -m options_strategy.eval.credit_check_full
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from options_strategy.eval.credit_check import run_credit_check
from options_strategy.eval.credit_check_preview import (
    band_edges_from_study,
    parity_fits,
)

WORLD_ROOT = Path("data/raw/thetadata/credit_check_slice/world")
STUDY_JSON = Path("reports/candle_study.json")
REPORT_MD = Path("reports/credit_check.md")

PRIMARY_SNAPSHOT_HMS = (15, 45, 0)
FRONT_WINDOWS = {"7d": (5, 9), "14d": (12, 16)}
EXIT_DTES = {"7d": (None,), "14d": (None, 7)}
RMSE_SENSITIVITY_CUT = 1.0
NEW_REGIMES = ("calm-2017", "volmageddon-feb-2018", "covid-mar-2020", "bear-2022")
CORNER_LABELS = {"q90", "q95", "atm_ref"}
GATE_MIN_FRAC = 0.20
GATE_PAUSE_REGIME_COUNT = 3


def entry_dates_from_study(study: dict) -> list[dict]:
    return [
        {
            "window": r["window"],
            "entry_date": dt.date.fromisoformat(r["entry_friday"]),
            "ema_state": r["ema_state"],
        }
        for r in study["f_purchase_spec"]
    ]


def primary_chain(world_root: Path, date: dt.date) -> pl.DataFrame | None:
    f = world_root / "option_quotes" / f"date={date}.parquet"
    if not f.exists():
        return None
    q = pl.read_parquet(f)
    h, m, s = PRIMARY_SNAPSHOT_HMS
    chain = q.filter(
        (pl.col("ts").dt.hour() == h)
        & (pl.col("ts").dt.minute() == m)
        & (pl.col("ts").dt.second() == s)
    )
    return None if chain.is_empty() else chain


def spot_for(world_root: Path, date: dt.date) -> float | None:
    bars = pl.read_parquet(world_root / "underlying_bars.parquet")
    h, m, _ = PRIMARY_SNAPSHOT_HMS
    row = bars.filter(
        (pl.col("ts").dt.date() == date)
        & (pl.col("ts").dt.hour() == h)
        & (pl.col("ts").dt.minute() == m)
    )
    return None if row.is_empty() else float(row["close"][0])


def run_full(
    world_root: Path = WORLD_ROOT, study_json: Path = STUDY_JSON
) -> tuple[pl.DataFrame, dict]:
    study = json.loads(study_json.read_text())
    edges = band_edges_from_study(study)
    manifest = json.loads((world_root / "manifest.json").read_text())

    frames, skipped = [], []
    for e in entry_dates_from_study(study):
        date = e["entry_date"]
        chain = primary_chain(world_root, date)
        spot = spot_for(world_root, date)
        if chain is None or spot is None:
            skipped.append(str(date))
            continue
        fits, diag = parity_fits(chain, date)
        sub = []
        for variant, front_window in FRONT_WINDOWS.items():
            df = run_credit_check(
                chain, spot, fits, date, edges[variant],
                front_dte_window=front_window, exit_dtes=EXIT_DTES[variant],
            )
            if df.height:
                sub.append(df.with_columns(pl.lit(variant).alias("front_variant")))
        if not sub:
            skipped.append(str(date))
            continue
        frames.append(
            pl.concat(sub).with_columns(
                pl.lit(e["window"]).alias("window"),
                pl.lit(e["ema_state"]).alias("ema_state"),
                pl.lit(spot).alias("spot"),
                pl.lit(diag["rmse_median"]).alias("parity_rmse_median"),
            )
        )
    if not frames:
        raise RuntimeError(f"no entry date produced structures; skipped={skipped}")
    rows = pl.concat(frames)
    meta = {
        "data_version": manifest["data_version"],
        "n_entries_priced": rows["session"].n_unique(),
        "n_entries_skipped": len(skipped),
        "skipped": skipped,
        "n_structures": rows.height,
    }
    return rows, meta


def agg_table(rows: pl.DataFrame) -> pl.DataFrame:
    return (
        rows.group_by(
            ["front_variant", "exit_mode", "label", "wing_offset"], maintain_order=True
        )
        .agg(
            pl.len().alias("n"),
            (pl.col("net_premium_pct_risk") > 0).mean().alias("frac_credit"),
            pl.col("net_premium_pct_risk").median().alias("med_net_prem_pct_risk"),
            pl.col("max_gain_pct_risk").median().alias("med_max_gain_pct_risk"),
            pl.col("thirty_pct_achievable").mean().alias("frac_30pct_ok"),
        )
        .sort(["front_variant", "exit_mode", "label", "wing_offset"])
    )


def corner_rows(rows: pl.DataFrame) -> pl.DataFrame:
    """Author-consistent corner: 14d fronts, q90/q95/atm_ref, any offset/exit."""
    return rows.filter(
        (pl.col("front_variant") == "14d") & pl.col("label").is_in(list(CORNER_LABELS))
    )


def gate_result(rows: pl.DataFrame) -> dict:
    """Per NEW regime: fraction of entry dates where ANY corner structure
    achieves +30% of risk. Pause if < GATE_MIN_FRAC in 3+ regimes."""
    corner = corner_rows(rows)
    per_regime: dict[str, dict] = {}
    n_below = 0
    for regime in NEW_REGIMES:
        sub = corner.filter(pl.col("window") == regime)
        if sub.is_empty():
            per_regime[regime] = {"n_dates": 0, "frac_dates_30pct": None}
            n_below += 1
            continue
        by_date = sub.group_by("session").agg(
            pl.col("thirty_pct_achievable").any().alias("ok")
        )
        frac = float(by_date["ok"].mean())
        per_regime[regime] = {"n_dates": by_date.height, "frac_dates_30pct": frac}
        if frac < GATE_MIN_FRAC:
            n_below += 1
    return {
        "per_regime": per_regime,
        "n_regimes_below_20pct": n_below,
        "pause": n_below >= GATE_PAUSE_REGIME_COUNT,
    }


def _fmt(t: pl.DataFrame) -> str:
    hdr = "| " + " | ".join(t.columns) + " |"
    sep = "|" + "---|" * len(t.columns)
    body = [
        "| " + " | ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in r) + " |"
        for r in t.rows()
    ]
    return "\n".join([hdr, sep, *body])


def write_report(rows: pl.DataFrame, meta: dict, gate: dict, out_md: Path = REPORT_MD) -> None:
    clean = rows.filter(pl.col("parity_rmse_median") <= RMSE_SENSITIVITY_CUT)
    n_cut = rows["session"].n_unique() - clean["session"].n_unique()

    sections = []
    for w in rows["window"].unique().sort().to_list():
        ww = rows.filter(pl.col("window") == w)
        sections.append(f"### {w} — all entry dates\n\n{_fmt(agg_table(ww))}")
        cw = clean.filter(pl.col("window") == w)
        if cw["session"].n_unique() != ww["session"].n_unique():
            sections.append(
                f"### {w} — sensitivity cut (parity RMSE <= {RMSE_SENSITIVITY_CUT})\n\n"
                f"{_fmt(agg_table(cw))}"
            )

    frac_credit_all = float((rows["net_premium_pct_risk"] > 0).mean())
    gate_lines = [
        f"- {r}: {v['frac_dates_30pct'] if v['frac_dates_30pct'] is not None else 'NO DATA'}"
        f" of {v['n_dates']} entry dates reach +30%R in the corner"
        for r, v in gate["per_regime"].items()
    ]
    verdict = (
        "## VERDICT\n\n"
        f"1. **Credit reading:** {frac_credit_all:.1%} of all {meta['n_structures']} structures "
        "priced as net credits at the 15:45 ET NBBO mid. The author's claim under the "
        "credit reading is "
        + ("**not refuted**" if frac_credit_all > 0.05 else "**refuted on real chains** "
           "(consistent with the synthetic 0/4096 and the EOD preview 0/552)")
        + ".\n"
        "2. **Return-on-risk reading (author-consistent corner: 14d fronts, q90/q95/atm_ref, "
        "offsets 0-50, either exit mode):**\n" + "\n".join(gate_lines) + "\n"
        f"3. **CONTINUE/PAUSE gate:** {gate['n_regimes_below_20pct']} of 4 new regimes below "
        f"{GATE_MIN_FRAC:.0%} → **{'PAUSE — awaiting user' if gate['pause'] else 'CONTINUE'}**.\n"
    )

    out_md.write_text(
        "# Credit check — FULL six-regime, REAL DATA (ThetaData STANDARD), 15:45 ET basis\n\n"
        "51-date mini-purchase spec slice; dual credit/debit reading (PLAN §1.6\n"
        "2026-08-16), ATM reference, 7d + 14d fronts, exit_mode {hold_to_expiry,\n"
        "exit_at_7dte} on 14d fronts (2026-08-18 amendment). Spot and rates\n"
        "context are parity-derived (no index subscription). Sensitivity cut per\n"
        "2026-08-18 amendment. Not investment advice.\n\n"
        f"- data_version: `{meta['data_version']}`\n"
        f"- entry Fridays priced: {meta['n_entries_priced']} of 51"
        f" (skipped: {meta['n_entries_skipped']} {meta['skipped']})\n"
        f"- structures priced: {meta['n_structures']}\n"
        f"- sensitivity cut removes {n_cut} entry dates (median parity RMSE > "
        f"{RMSE_SENSITIVITY_CUT} pt)\n\n"
        + verdict
        + "\n## Aggregates by regime window\n\n"
        + "\n\n".join(sections)
        + "\n"
    )


def main() -> int:
    import hashlib

    from options_strategy import ledger

    rows, meta = run_full()
    gate = gate_result(rows)
    write_report(rows, meta, gate)
    cfg = json.dumps(
        {
            "eval": "credit_check_full",
            "snapshot": "15:45:00",
            "front_windows": FRONT_WINDOWS,
            "exit_dtes": {k: [str(x) for x in v] for k, v in EXIT_DTES.items()},
            "rmse_cut": RMSE_SENSITIVITY_CUT,
            "gate": {"min_frac": GATE_MIN_FRAC, "pause_count": GATE_PAUSE_REGIME_COUNT},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    ledger.append(
        [
            ledger.LedgerRow(
                kind="credit_check_full",
                config_hash=hashlib.sha256(cfg.encode("ascii")).hexdigest(),
                git_sha=ledger.current_git_sha(),
                data_version=meta["data_version"],
                seed=0,
                metrics={
                    "n_entries_priced": meta["n_entries_priced"],
                    "n_structures": meta["n_structures"],
                    "frac_credit_all": float((rows["net_premium_pct_risk"] > 0).mean()),
                    "gate_regimes_below": gate["n_regimes_below_20pct"],
                    "gate_pause": gate["pause"],
                },
                artifacts=[str(REPORT_MD)],
            )
        ]
    )
    print(json.dumps({**meta, "gate": gate}, indent=2))
    return 2 if gate["pause"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
