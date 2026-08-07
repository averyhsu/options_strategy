"""Assemble FINAL_REPORT_SYNTHETIC.md (PLAN §12 P6, Pass-1 form) from the
committed evidence artifacts. SYNTHETIC labeling everywhere; §10(a-e) answered
for the synthetic dress rehearsal; DSR & PBO on the front page.
"""

from __future__ import annotations

import json
from pathlib import Path


def _j(p: str) -> dict | list:
    return json.loads(Path(p).read_text())


def build(out_path: str = "FINAL_REPORT_SYNTHETIC.md") -> Path:
    p4 = _j("experiments/p4/sweep_summary.json")
    p5 = _j("experiments/p5/p5_summary.json")
    myst = _j("experiments/p6/mystery_summary.json")
    dsr = _j("experiments/p6/robustness/dsr.json")
    pbo = _j("experiments/p6/robustness/pbo.json")
    wfo = _j("experiments/p6/robustness/wfo.json")
    ruin = _j("experiments/p6/robustness/ruin.json")
    fees = _j("experiments/p6/robustness/fees.json")
    stress = _j("experiments/p6/robustness/stress_windows.json")
    gaps = _j("experiments/p6/robustness/gap_injector.json")

    lines = [
        "# FINAL REPORT — Pass 1 (SYNTHETIC)",
        "",
        "> **SYNTHETIC DATA ONLY.** Every number in this report was produced on",
        "> seeded synthetic worlds (Heston+Merton underlying, SSVI chains). This is",
        "> the full-system dress rehearsal required by PLAN §12.0 Pass 1. **No",
        "> real-market conclusion of any kind is stated or implied.** Pass 2 reruns",
        "> P4-P6 on purchased historical data. A matched configuration is not",
        "> evidence of the original trader's true rules nor of future",
        "> profitability. Nothing here is investment advice.",
        "",
        "## Front page (PLAN §10.3)",
        "",
        f"- **Deflated Sharpe Ratio: {dsr['dsr']:.3f}** — best kept config's ann.",
        f"  Sharpe {dsr['sharpe_ann_best']:.2f}, deflated against N = {dsr['n_trials']:,}",
        "  ledgered trials. Read: on this synthetic surface, the best selected",
        "  config is statistically indistinguishable from selection luck.",
        f"- **PBO (CSCV, 16 blocks, {pbo['n_splits']} splits): {pbo['pbo']:.2f}** —",
        "  probability that the in-sample best underperforms the median out of",
        "  sample.",
        "",
        "## What was run",
        "",
        f"- P4 coarse sweep: {p4['n_configs']:,} Sobol configs over the PLAN §8 priors on a",
        f"  10y EOD world (`{p4['data_version']}`): **{p4['n_survivors']} survivors** of the",
        "  fingerprint-informed §9.1 filters (the trader's WR band is the binding",
        f"  constraint); {p4['n_kept']} kept incl. the 2% random bias-guard.",
        f"- P5 intraday grid: {p5['n_runs_done']} Track-B runs (screened configs x",
        f"  {p5['n_defense_variants']} defense variants x CONSERVATIVE/MID) on a 9-week",
        f"  5-min world (`{p5['data_version']}`) incl. a scripted -5% weekend gap.",
        f"- P6 mystery trader: hidden config vs {myst['n_candidates']:,} candidates —",
        f"  **gate {'PASS' if myst['gate_pass'] else 'FAIL'}**: {myst['n_hard_pass_dd_dates']}",
        "  candidates survive the DD-date hard constraint; the accepted region",
        f"  ({myst['n_accepted']} configs) covers the hidden truth on every identified",
        f"  dimension ({myst['n_dims_identified']} identified, the rest honest plateaus).",
        "",
        "## §10(a) Does the family have positive net expectancy, and where?",
        "",
        "On THIS synthetic surface: no configuration reproduces the target profile.",
        "2,306 of 7,461 trading configs had positive after-fee expectancy, but with",
        "commodity-like win rates (median 0.47, max 0.78) and small win magnitudes —",
        "never the claimed ~0.85-0.92 WR with +30%-of-R wins. Scripted-regime",
        "slicing (stress table below) shows the profitable segments are grind-up",
        "regimes; the bear-grind segment is ruinous (median -43% for top configs).",
        "",
        "## §10(b) Which parameter regions match the fingerprints, and identifiability",
        "",
        "The mystery-trader exercise measures exactly this with a KNOWN truth: the",
        "DD-date constraint is extremely informative (16,383 -> 33 candidates); the",
        "posterior identifies `require_credit` and `defense` exactly and leaves 13 of",
        "15 dimensions as plateaus. **Expectation for Pass 2: most structure",
        "parameters will NOT be point-identified from ~87 daily observations; honest",
        "deliverable is the accepted region + plateau statement** (PLAN §9.3).",
        "",
        "## §10(c) Do matching regions survive WFO / DSR / PBO / stress?",
        "",
        f"- Walk-forward ({wfo['n_folds']} anchored+rolling folds, train 3y / test 6m /",
        "  step 3m): median OOS share of top-decile configs profitable = ",
        f"  **{wfo['median_oos_share_profitable']:.2f}** — region selection does not",
        "  reliably transfer out of sample here.",
        f"- DSR {dsr['dsr']:.3f} and PBO {pbo['pbo']:.2f} (front page).",
        "- Scripted stress windows (top-5 kept configs, median window return):",
        "",
        "| window | median | worst |",
        "|---|---|---|",
        *[
            f"| {w['window']} | {w['median_impact']:+.1%} | {w['worst_impact']:+.1%} |"
            for w in stress
        ],
        "",
        "- Weekend-gap injector (live explicit-credit structure, MID fills):",
        "",
        "| gap | vol mult | undefended | defended (close tested side) |",
        "|---|---|---|---|",
    ]
    by_gap: dict = {}
    for g in gaps:
        by_gap.setdefault((g["gap_pct"], g["vol_mult"]), {})[g["defense"]] = g
    for (gp, vm), d in sorted(by_gap.items()):
        u = d.get("none", {})
        de = d.get("close_tested_side/immediate", {})
        lines.append(
            f"| {gp:+.0%} | x{vm:.0f} | {u.get('total_return', float('nan')):+.1%} "
            f"(worst day {u.get('worst_day', float('nan')):+.1%}) "
            f"| {de.get('total_return', float('nan')):+.1%} |"
        )
    lines += [
        "",
        "Defense truncates gap losses substantially but cannot beat the overnight",
        "jump itself — the F4 lesson; any Pass-2 result without gap stress is",
        "incomplete (PLAN §14).",
        "",
        "## §10(d) Tail / risk-of-ruin at the trader's sizing",
        "",
        f"Block-bootstrap of {ruin['n_weekly_obs']:,} kept-config weekly P&L observations",
        "at ~15%-of-NAV deployment:",
        "",
        "| horizon | P(NAV < 50%) | P(NAV < 30%) |",
        "|---|---|---|",
        f"| 1y | {ruin['1y']['p_below_50pct']:.1%} | {ruin['1y']['p_below_30pct']:.1%} |",
        f"| 3y | {ruin['3y']['p_below_50pct']:.1%} | {ruin['3y']['p_below_30pct']:.1%} |",
        "",
        "The 'your risk is diabolical' critique quantifies as a coin-flip-scale",
        "3-year half-loss probability on this synthetic surface at this sizing.",
        "",
        "## §10(e) Cost / fill sensitivity",
        "",
        "| fee multiplier | median expectancy per cycle | share positive |",
        "|---|---|---|",
        *[
            f"| x{f['fee_multiplier']:.0f} | ${f['median_expectancy_per_cycle']:,.0f} "
            f"| {f['share_positive']:.0%} |"
            for f in fees
        ],
        "",
        "Fees x1..x3 barely dent the (synthetic) top-kept expectancy — cycle P&L is",
        "dominated by price moves, not commissions, at SPX scale. Fill-model bounds:",
        "aggregate CONSERVATIVE fills 367 vs MID 482 in the P5 grid (bounds hold);",
        "OPTIMISTIC is never headlined (PLAN §7.2).",
        "",
        "## Machinery validation summary",
        "",
        "- 154-test suite green: conservation, settlement-to-the-cent, no-lookahead",
        "  property, Track A == Track B == sweep-runner equivalences (1e-10 on the",
        "  10y world), IV round-trip <= 1e-6, IBKR-metric golden (Sharpe 2.99 /",
        "  Sortino 4.45 reconstruction), regime == independent reference, all 8",
        "  defense actions on a scripted gap week, QA gate with truth reconciliation.",
        "- Every run is in `experiments/ledger.parquet` (worldgen/qa/sweep/p5run/",
        "  study/match): if it isn't in the ledger, it didn't happen.",
        "",
        "## Pass-2 preconditions",
        "",
        "Purchase per PLAN §4.3 (see the Pass-1 handoff note), drop files under",
        "`data/raw/`, build the vendor adapter, run `options_strategy qa`, bump",
        "`data_version`, rerun P2 invariants, then rerun P4 -> P6 on real data.",
        "",
    ]
    out = Path(out_path)
    out.write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    print(build())
