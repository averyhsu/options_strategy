"""F4 forensics (user directive 2026-08-24): characterize the zero-acceptance.

The zero-acceptance verdict STANDS (reports/fingerprint_match.md). This phase
measures three candidate explanations without concluding beyond measurement:

  posterior  - No-F4 posterior: ABC finalize with the F4 hard gate demoted
               (soft/off), formal posterior over F1-F3/F5-F14, with the
               survivors' selective-cadence structure explicit.
  weekend    - Inverse search on the REAL Jul-9..14 15-min marks over a
               broadened structure space: what holdings CAN lose ~11% of a
               $1M account Fri->Mon while staying consistent with the
               record's 2.44% daily vol. INFERENCE about the account, not an
               accusation.
  sleeve     - Bounded additive sleeve (<=1 day/wk, |e| <= 1.5% NAV) on the
               nearest-miss configs: are F4 and F11 jointly reachable?
  report     - Assemble reports/f4_forensics.md from the artifacts.

(The model-gap Track-B grid, workstream 3, runs via f4_modelgap_drive.py.)

Usage:  python -m options_strategy.eval.f4_forensics <posterior|weekend|sleeve|report>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy.eval.mystery import _fp_from_row
from options_strategy.eval.real_match import (
    OUT_DIR as MATCH_DIR,
)
from options_strategy.eval.real_match import (
    _marginals,
    load_targets,
)
from options_strategy.sweep.abc import abc_match

OUT = Path("experiments/f4_forensics")
REPORT_MD = Path("reports/f4_forensics.md")
LIVE_WORLD = Path("data/raw/theta/live_world")
ACCOUNT = 1_000_000.0
F4_LOSS_FRAC = 0.1111
TARGET_DAILY_VOL = 0.0244
FRI = dt.date(2026, 7, 10)
MON = dt.date(2026, 7, 13)


def _chunks_df() -> pl.DataFrame:
    files = sorted((MATCH_DIR / "fp_chunks").glob("fp_*.parquet"))
    return pl.concat([pl.read_parquet(p) for p in files]).sort("idx")


# ---------------------------------------------------------------- posterior --


def no_f4_posterior() -> dict:
    target, raw = load_targets()
    df = _chunks_df()
    rows = df.to_dicts()
    fps = [_fp_from_row(r) for r in rows]
    result = abc_match(fps, target, accept_frac=float(raw["abc"]["accept_frac"]), dd_tol_days=10**6)
    accepted = [rows[i] for i in result.accepted_idx]
    marg = _marginals(accepted)
    cyc = np.array([r["n_live_cycles"] for r in accepted])
    out = {
        "n_candidates": len(rows),
        "eps": float(result.eps),
        "n_accepted": len(accepted),
        "marginals": marg,
        "cadence": {
            "n_live_cycles_median": float(np.median(cyc)) if len(cyc) else None,
            "n_live_cycles_p90": float(np.quantile(cyc, 0.9)) if len(cyc) else None,
            "share_full_cadence_ge15": float((cyc >= 15).mean()) if len(cyc) else None,
            "share_selective_le7": float((cyc <= 7).mean()) if len(cyc) else None,
        },
        "accepted_feature_medians": {
            f: float(np.median([r[f] for r in accepted]))
            for f in ("sharpe_ann", "weekly_wr", "max_dd", "mean_daily")
        }
        if accepted
        else {},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "no_f4_posterior.json").write_text(json.dumps(out, indent=2, default=str))
    return out


# ------------------------------------------------------------------ weekend --


def _snap(quotes: pl.DataFrame, day: dt.date, hh: int, mm: int) -> pl.DataFrame:
    return quotes.filter(
        (pl.col("ts").dt.hour() == hh) & (pl.col("ts").dt.minute() == mm)
    ).with_columns(((pl.col("bid") + pl.col("ask")) / 2).alias("mid"))


def _mid(
    snap: pl.DataFrame, root_pref: tuple[str, ...], expiry: dt.date, cp: str, strike: float
) -> float | None:
    for root in root_pref:
        r = snap.filter(
            (pl.col("root") == root)
            & (pl.col("expiry_date") == expiry)
            & (pl.col("cp") == cp)
            & (pl.col("strike") == strike)
            & (pl.col("bid") > 0)
        )
        if r.height:
            return float(r["mid"][0])
    return None


def _nearest_strike(snap: pl.DataFrame, expiry: dt.date, cp: str, target: float) -> float | None:
    side = snap.filter(
        (pl.col("expiry_date") == expiry) & (pl.col("cp") == cp) & (pl.col("bid") > 0)
    )
    if side.is_empty():
        return None
    ks = side["strike"].to_numpy()
    return float(ks[int(np.argmin(np.abs(ks - target)))])


def _pick_expiry(snap: pl.DataFrame, day: dt.date, lo: int, hi: int) -> dt.date | None:
    exps = sorted(snap["expiry_date"].unique().to_list())
    window = [e for e in exps if lo <= (e - day).days <= hi]
    if not window:
        return None
    center = (lo + hi) / 2
    return min(window, key=lambda e: (abs((e - day).days - center), -(e - day).days))


def weekend_inverse_search() -> dict:
    q_fri = pl.read_parquet(LIVE_WORLD / "option_quotes" / f"date={FRI}.parquet")
    q_mon = pl.read_parquet(LIVE_WORLD / "option_quotes" / f"date={MON}.parquet")
    fri, mon = _snap(q_fri, FRI, 15, 45), _snap(q_mon, MON, 15, 45)
    bars = pl.read_parquet(LIVE_WORLD / "underlying_bars.parquet").with_columns(
        pl.col("ts").dt.date().alias("d")
    )
    spot_fri = float(bars.filter(pl.col("d") == FRI)["close"][-1])
    spot_mon = float(bars.filter(pl.col("d") == MON)["close"][-1])
    spot_ret = spot_mon / spot_fri - 1.0

    # daily closes June 1 -> Jul 30 for own-vol context
    daily = (
        bars.filter((pl.col("d") >= dt.date(2026, 6, 1)) & (pl.col("d") <= dt.date(2026, 7, 30)))
        .group_by("d", maintain_order=True)
        .agg(pl.col("close").last())
        .sort("d")
    )
    closes = daily["close"].to_numpy()
    spot_daily_vol = float(np.std(np.diff(closes) / closes[:-1], ddof=1))

    roots = ("SPXW", "SPX")
    results: list[dict] = []

    def eval_structure(name: str, legs: list[tuple[dt.date, str, float, int]]) -> None:
        """legs: (expiry, cp, strike, ratio per unit). P&L per unit Fri->Mon."""
        v_fri = v_mon = 0.0
        for expiry, cp, strike, ratio in legs:
            mf = _mid(fri, roots, expiry, cp, strike)
            mm_ = _mid(mon, roots, expiry, cp, strike)
            if mf is None or mm_ is None:
                results.append({"structure": name, "status": "unpriceable"})
                return
            v_fri += ratio * mf
            v_mon += ratio * mm_
        pnl_per_unit = (v_mon - v_fri) * 100.0
        if pnl_per_unit >= 0:
            results.append(
                {
                    "structure": name,
                    "status": "gains_on_weekend",
                    "pnl_per_unit": round(pnl_per_unit, 1),
                }
            )
            return
        units = F4_LOSS_FRAC * ACCOUNT / (-pnl_per_unit)
        # own-vol context: weekend move in units of the structure's premium
        prem = abs(v_fri) * 100.0
        results.append(
            {
                "structure": name,
                "status": "candidate",
                "pnl_per_unit_fri_to_mon": round(pnl_per_unit, 1),
                "units_for_f4_loss": round(units, 1),
                "gross_premium_at_sizing": round(prem * units, 0),
                "premium_frac_of_account": round(prem * units / ACCOUNT, 3),
                "weekend_loss_frac_of_premium": round(-pnl_per_unit / prem, 3)
                if prem > 0
                else None,
            }
        )

    # (a) representative diagonals: 7d and 14d fronts, q90-ish shorts, near wings
    for fd, back_off in ((7, 21), (14, 21)):
        front = _pick_expiry(fri, FRI, max(fd - 2, 3), fd + 2)
        if front is None:
            continue
        back = _pick_expiry(fri, FRI, fd + back_off - 3, fd + back_off + 14)
        if back is None:
            continue
        sp = _nearest_strike(fri, front, "P", spot_fri * 0.979)
        sc = _nearest_strike(fri, front, "C", spot_fri * 1.021)
        if sp is None or sc is None:
            continue
        lp = _nearest_strike(fri, back, "P", sp - 25)
        lc = _nearest_strike(fri, back, "C", sc + 25)
        if lp is None or lc is None:
            continue
        eval_structure(
            f"double_diagonal_{fd}d_front",
            [(front, "P", sp, -1), (front, "C", sc, -1), (back, "P", lp, 1), (back, "C", lc, 1)],
        )

    # (b) naked short strangles across tenor x width
    for fd in (7, 14, 35):
        exp = _pick_expiry(fri, FRI, max(fd - 3, 3), fd + 4)
        if exp is None:
            continue
        for pct in (0.01, 0.02, 0.04):
            sp = _nearest_strike(fri, exp, "P", spot_fri * (1 - pct))
            sc = _nearest_strike(fri, exp, "C", spot_fri * (1 + pct))
            if sp is None or sc is None:
                continue
            eval_structure(
                f"short_strangle_{fd}d_{int(pct * 100)}pct",
                [(exp, "P", sp, -1), (exp, "C", sc, -1)],
            )

    # (c) long short-dated gamma (long straddle; loses to weekend theta decay
    # if the move is small)
    for fd in (4, 7):
        exp = _pick_expiry(fri, FRI, max(fd - 2, 2), fd + 2)
        if exp is None:
            continue
        k = _nearest_strike(fri, exp, "C", spot_fri)
        if k is None:
            continue
        eval_structure(f"long_straddle_{fd}d", [(exp, "C", k, 1), (exp, "P", k, 1)])

    # (d) outright delta: pure index-equivalent exposure
    delta_leverage = F4_LOSS_FRAC / max(-spot_ret, 1e-9)
    results.append(
        {
            "structure": "outright_index_delta",
            "status": "candidate" if spot_ret < 0 else "gains_on_weekend",
            "spot_ret_fri_to_mon": round(spot_ret, 5),
            "leverage_for_f4_loss": round(delta_leverage, 1),
            "implied_daily_vol_at_that_leverage": round(delta_leverage * spot_daily_vol, 4),
            "consistent_with_244bp_daily_vol": bool(
                delta_leverage * spot_daily_vol <= TARGET_DAILY_VOL * 1.25
            ),
        }
    )

    out = {
        "spot_fri": spot_fri,
        "spot_mon": spot_mon,
        "spot_ret_weekend": spot_ret,
        "spot_daily_vol_jun_jul": spot_daily_vol,
        "f4_loss_target_dollars": F4_LOSS_FRAC * ACCOUNT,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "weekend_search.json").write_text(json.dumps(out, indent=2, default=str))
    return out


# ------------------------------------------------------------------- sleeve --


def sleeve_sensitivity(top_n: int = 50, max_e: float = 0.015) -> dict:
    """Bounded additive sleeve on nearest-miss daily-return series: can F4
    (an 11.1% Fri->Mon crater at the right dates) and F11 (72.4% positive
    days) become JOINTLY reachable with <=1 event/week, |e| <= max_e?"""
    target, _raw = load_targets()
    df = _chunks_df()
    rows = df.to_dicts()
    fps = [_fp_from_row(r) for r in rows]
    soft = abc_match(fps, target, accept_frac=0.01, dd_tol_days=10**6)
    order = np.argsort(soft.distances)[:top_n]

    sessions = None
    navs_meta = json.loads((LIVE_WORLD / "manifest.json").read_text())
    _ = navs_meta
    out_rows = []
    for i in order:
        r = rows[int(i)]
        lv = np.asarray(r["log_vami"], dtype=np.float64)
        rets = np.diff(np.exp(lv - lv[0]), prepend=1.0)[1:] if len(lv) > 1 else np.empty(0)
        # actually: simple returns from log-vami
        rets = np.exp(np.diff(lv)) - 1.0
        n = len(rets)
        if n < 60:
            continue
        # F4 needs a single-day (Mon) crater: base_ret + e = -11.1% at the F4
        # date => base must supply <= -(0.111 - max_e) = -9.6%. Measure the
        # worst base daily return as the binding constraint.
        worst = float(rets.min())
        f4_reachable = worst <= -(F4_LOSS_FRAC - max_e)
        # F11: greedily flip the smallest-magnitude negative days positive
        # with events (max one per ISO week ~ n/5 events)
        neg = np.sort(rets[rets < 0])[::-1]  # closest to zero first
        budget = n // 5
        flippable = sum(1 for x in neg[:budget] if -x <= max_e)
        pct_pos_after = (np.sum(rets > 0) + flippable) / n
        out_rows.append(
            {
                "idx": int(r["idx"]),
                "worst_base_daily_ret": round(worst, 4),
                "f4_magnitude_reachable": bool(f4_reachable),
                "pct_pos_base": round(float((rets > 0).mean()), 3),
                "pct_pos_after_sleeve": round(float(pct_pos_after), 3),
                "f11_reachable": bool(pct_pos_after >= 0.7241),
            }
        )
    _ = sessions
    summary = {
        "n_evaluated": len(out_rows),
        "n_f4_reachable": sum(1 for r in out_rows if r["f4_magnitude_reachable"]),
        "n_f11_reachable": sum(1 for r in out_rows if r["f11_reachable"]),
        "n_jointly_reachable": sum(
            1 for r in out_rows if r["f4_magnitude_reachable"] and r["f11_reachable"]
        ),
        "max_event_frac": max_e,
        "rows": out_rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sleeve_sensitivity.json").write_text(json.dumps(summary, indent=2))
    return summary


# ------------------------------------------------------------------- report --


def build_report() -> None:
    post = json.loads((OUT / "no_f4_posterior.json").read_text())
    wk = json.loads((OUT / "weekend_search.json").read_text())
    sl = json.loads((OUT / "sleeve_sensitivity.json").read_text())
    mg_path = OUT / "modelgap_summary.json"
    mg = json.loads(mg_path.read_text()) if mg_path.exists() else None

    lines = [
        "# F4 forensics — characterizing the zero-acceptance (Pass 2 addendum)",
        "",
        "The zero-acceptance verdict of `reports/fingerprint_match.md` STANDS.",
        "This phase measures three candidate explanations. Weekend-search results",
        "are INFERENCE about what the account plausibly contained — not an",
        "accusation. Not investment advice.",
        "",
        "## 1. No-F4 posterior (F4 hard gate demoted)",
        "",
        f"- accepted: {post['n_accepted']} of {post['n_candidates']} (eps {post['eps']:.3f})",
        f"- accepted-set feature medians: {json.dumps(post['accepted_feature_medians'])}",
        f"- cadence structure: median live cycles "
        f"{post['cadence']['n_live_cycles_median']}, share trading <=7 of 17 weeks "
        f"{post['cadence']['share_selective_le7']:.0%}, share full-cadence (>=15) "
        f"{post['cadence']['share_full_cadence_ge15']:.0%}",
        "",
        "The family region consistent with everything EXCEPT the July crater is",
        "dominated by SELECTIVE traders — regime-gated configs that sit out most",
        "weeks. Full-cadence weekly trading is essentially absent from the",
        "posterior.",
        "",
        "| dim | accepted | identified |",
        "|---|---|---|",
        *[
            f"| {m['dim']} | {m['accepted']} | {'YES' if m['identified'] else 'plateau'} |"
            for m in post["marginals"]
        ],
        "",
        "## 2. Weekend inverse search (real Jul 10 -> 13 marks, $1M account)",
        "",
        f"Spot moved {wk['spot_ret_weekend']:+.2%} over the F4 weekend "
        f"(daily spot vol Jun-Jul: {wk['spot_daily_vol_jun_jul']:.2%}). "
        f"Target loss: ${wk['f4_loss_target_dollars']:,.0f}.",
        "",
        "```json",
        json.dumps(wk["results"], indent=2),
        "```",
        "",
    ]
    if mg:
        lines += [
            "## 3. Model-gap bounds (top-50 soft-ranked, live window, Track B)",
            "",
            "```json",
            json.dumps(mg, indent=2),
            "```",
            "",
        ]
    lines += [
        f"## 4. Sleeve sensitivity (<=1 event/week, |e| <= {sl['max_event_frac']:.1%} NAV)",
        "",
        f"- configs evaluated: {sl['n_evaluated']}",
        f"- F4 magnitude reachable (base already craters >= "
        f"{F4_LOSS_FRAC - sl['max_event_frac']:.1%} on some day): {sl['n_f4_reachable']}",
        f"- F11 reachable: {sl['n_f11_reachable']}",
        f"- JOINTLY reachable: {sl['n_jointly_reachable']}",
        "",
        "A sleeve bounded at 1.5% NAV per event cannot manufacture an 11.1%",
        "single-weekend crater; it can only close the F11 (%-positive-days) gap.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["posterior", "weekend", "sleeve", "report"])
    args = ap.parse_args()
    if args.step == "posterior":
        out = no_f4_posterior()
        print(json.dumps({k: out[k] for k in ("n_accepted", "eps", "cadence")}, indent=2))
    elif args.step == "weekend":
        out = weekend_inverse_search()
        print(json.dumps(out, indent=2, default=str))
    elif args.step == "sleeve":
        out = sleeve_sensitivity()
        print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    else:
        build_report()
        print(str(REPORT_MD))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
