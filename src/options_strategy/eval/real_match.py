"""Pass-2 ABC fingerprint match: REAL live window vs the REAL targets.

Reuses the P6 machinery verbatim where it exists (fp_chunk fingerprints every
space-v4 sobol candidate over 2026-04-01..07-30 on the real live world;
abc_match does the distance/acceptance) — the only new parts are the target
vector loaded from configs/fingerprints.yaml (the IBKR screenshot values;
no daily VAMI path exists, so the curve term does not bind) and a posterior
report WITHOUT a truth column: on real data there is nothing to "recover",
only a posterior and an identifiability statement (PLAN §9.3).

Usage:  python -m options_strategy.eval.real_match [--chunk N]   # one chunk
        python -m options_strategy.eval.real_match --finalize     # match+report
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from options_strategy import ledger
from options_strategy.eval.metrics_ibkr import Fingerprints
from options_strategy.eval.mystery import CHUNK, _fp_from_row, fp_chunk
from options_strategy.sweep.abc import abc_match
from options_strategy.sweep.space import DIM_NAMES

WORLD_ROOT = "data/raw/theta/live_world"
OUT_DIR = Path("experiments/p2_match")
TARGETS_YAML = Path("configs/fingerprints.yaml")
REPORT_MD = Path("reports/fingerprint_match.md")

# space v4 categorical cardinalities (v3 set + exit_mode)
CATEGORICAL_DIMS = {
    "threshold_reference": 3,
    "require_credit": 2,
    "regime_action": 4,
    "ema_len": 3,
    "hysteresis": 3,
    "defense": 2,
    "risk_definition": 3,
    "risk_fraction": 3,
    "strike_family": 2,
    "wing_family": 2,
    "front_dte": 2,
    "exit_mode": 2,
}
NUMERIC_PRIOR_SPAN = {
    "short_put_delta": 0.45,
    "short_call_delta": 0.45,
    "long_put_offset_days": 49,
    "long_call_offset_days": 49,
    "long_strike_offset": 100,
    "credit_threshold_frac": 0.40,
    "min_credit_frac": 0.20,
    "coverage_q_put": 0.15,
    "coverage_q_call": 0.15,
}


def load_targets(path: Path = TARGETS_YAML) -> tuple[Fingerprints, dict]:
    raw = yaml.safe_load(path.read_text())
    t = raw["targets"]
    fp = Fingerprints(
        sharpe_ann=t["sharpe_ann"],
        sortino_ann=t["sortino_ann"],
        std_daily=t["std_daily"],
        downside_dev_daily=t["downside_dev_daily"],
        mean_daily=t["mean_daily"],
        pct_positive=t["pct_positive"],
        max_dd=t["max_dd"],
        dd_peak_date=t["dd_peak_date"],
        dd_valley_date=t["dd_valley_date"],
        recovery_days=t["recovery_days"],
        weekly_wr=t["weekly_wr"],
        median_win_pct_r=t["median_win_pct_r"],
        log_vami=np.empty(0),  # no daily path published -> curve term inert
    )
    return fp, raw


def _marginals(accepted: list[dict]) -> list[dict]:
    rows = []
    for dim in DIM_NAMES:
        vals = [r[dim] for r in accepted]
        if dim in CATEGORICAL_DIMS:
            counts: dict[str, int] = {}
            for v in vals:
                counts[str(v)] = counts.get(str(v), 0) + 1
            values = sorted(counts)
            rows.append(
                {
                    "dim": dim,
                    "accepted": ", ".join(f"{v} ({counts[v]})" for v in values) or "-",
                    "identified": 0 < len(values) < CATEGORICAL_DIMS[dim],
                }
            )
        else:
            arr = np.array(vals, dtype=np.float64)
            if len(arr) == 0:
                rows.append({"dim": dim, "accepted": "-", "identified": False})
                continue
            lo, hi = float(arr.min()), float(arr.max())
            rows.append(
                {
                    "dim": dim,
                    "accepted": f"[{lo:.4g}, {hi:.4g}] med {float(np.median(arr)):.4g}",
                    "identified": (hi - lo) < 0.5 * NUMERIC_PRIOR_SPAN[dim],
                }
            )
    return rows


def finalize() -> dict:
    target, raw = load_targets()
    abc_cfg = raw["abc"]
    n_candidates = int(abc_cfg["n_candidates"])
    chunks = sorted((OUT_DIR / "fp_chunks").glob("fp_*.parquet"))
    df = pl.concat([pl.read_parquet(p) for p in chunks]).sort("idx")
    if df.height != n_candidates:
        raise RuntimeError(f"fingerprint chunks cover {df.height}/{n_candidates}")
    rows = df.to_dicts()
    fps = [_fp_from_row(r) for r in rows]

    result = abc_match(
        fps,
        target,
        accept_frac=float(abc_cfg["accept_frac"]),
        dd_tol_days=int(abc_cfg["dd_tol_days"]),
    )
    accepted = [rows[i] for i in result.accepted_idx]
    marg = _marginals(accepted)
    n_identified = sum(1 for m in marg if m["identified"])

    # Zero-acceptance diagnosis: rank WITHOUT the F4 hard gate so the report
    # shows HOW FAR the nearest candidates sit, not just that none passed.
    nearest: list[dict] = []
    if not accepted:
        soft = abc_match(fps, target, accept_frac=float(abc_cfg["accept_frac"]), dd_tol_days=10**6)
        order = np.argsort(soft.distances)[:10]
        for i in order:
            r = rows[int(i)]
            nearest.append(
                {
                    "dist": float(soft.distances[int(i)]),
                    "n_live_cycles": r["n_live_cycles"],
                    "sharpe": round(r["sharpe_ann"], 2),
                    "weekly_wr": (
                        round(r["weekly_wr"], 3) if r["weekly_wr"] == r["weekly_wr"] else None
                    ),
                    "max_dd": round(r["max_dd"], 4),
                    "dd_peak": str(r["dd_peak_date"]),
                    "dd_valley": str(r["dd_valley_date"]),
                    "strike_family": r["strike_family"],
                    "front_dte": r["front_dte"],
                    "exit_mode": r["exit_mode"],
                    "defense": r["defense"],
                }
            )

    world_manifest = json.loads((Path(WORLD_ROOT) / "manifest.json").read_text())
    summary = {
        "data_version": world_manifest["data_version"],
        "n_candidates": n_candidates,
        "n_hard_pass_dd_gate": int(result.n_hard_pass),
        "eps": float(result.eps),
        "n_accepted": len(accepted),
        "n_dims_identified": n_identified,
        "median_accepted_n_live_cycles": (
            float(np.median([r["n_live_cycles"] for r in accepted])) if accepted else None
        ),
    }

    lines = [
        "# ABC fingerprint match — REAL live window vs REAL targets (Pass 2)",
        "",
        "Space v4 (21 dims incl. exit_mode) over the REAL 15-min live world "
        f"(`{world_manifest['data_version']}`, {world_manifest['n_sessions']} sessions); "
        "targets from configs/fingerprints.yaml (IBKR screenshots, PLAN §2). "
        "The published record has no daily VAMI path, so the curve-distance "
        "term does not bind; the F4 drawdown-date window (±2d) is the hard "
        "gate. Not investment advice.",
        "",
        "## Summary",
        "",
        *[f"- {k}: {v}" for k, v in summary.items()],
        "",
        "## Posterior marginals (accepted set)",
        "",
        "| dim | accepted | identified |",
        "|---|---|---|",
        *[
            f"| {m['dim']} | {m['accepted']} | {'YES' if m['identified'] else 'plateau'} |"
            for m in marg
        ],
        "",
        "## Identifiability statement",
        "",
        f"{n_identified} of {len(DIM_NAMES)} dimensions identified (accepted set a "
        "strict subset of the prior); the remainder are plateaus — the honest "
        "expected outcome per PLAN §9.3. Dims marked YES constitute 'the family "
        "that matches'; plateau dims are unconstrained by the published record.",
        "",
    ]
    if nearest:
        lines += [
            "## Zero-acceptance diagnosis (nearest candidates, F4 gate disabled)",
            "",
            "| dist | cycles | sharpe | wr | maxDD | dd peak->valley "
            "| family | front | exit | defense |",
            "|---|---|---|---|---|---|---|---|---|---|",
            *[
                f"| {m['dist']:.2f} | {m['n_live_cycles']} | {m['sharpe']} | {m['weekly_wr']} "
                f"| {m['max_dd']} | {m['dd_peak']}->{m['dd_valley']} | {m['strike_family']} "
                f"| {m['front_dte']} | {m['exit_mode']} | {m['defense']} |"
                for m in nearest
            ],
            "",
            "**Reading:** zero candidates pass the F4 drawdown-date hard gate, and the "
            "nearest soft-ranked candidates sit far from the targets on the scalar "
            "features as well. On this data and under this model of the family "
            "(EOD-mid fills at the 15:45 basis, {none, close-tested-side} defense, "
            "dual strike families, 7d/14d fronts with optional exit-at-7dte), NO "
            "parameter region reproduces the published live record. Model gaps that "
            "could account for the mismatch (not evidence of the record's veracity "
            "either way): richer defense/rolling than the collapsed proxy, resting "
            "intraday credit-order fills vs EOD-mid, and any non-diagonal activity "
            "in the account beyond the acceptance tolerance.",
            "",
        ]
    REPORT_MD.write_text("\n".join(lines))

    cfg_str = json.dumps(
        {
            "eval": "real_match",
            "targets": {k: str(v) for k, v in raw["targets"].items()},
            "abc": abc_cfg,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    ledger.append(
        [
            ledger.LedgerRow(
                kind="fingerprint_match_real",
                config_hash=hashlib.sha256(cfg_str.encode("ascii")).hexdigest(),
                git_sha=ledger.current_git_sha(),
                data_version=world_manifest["data_version"],
                seed=int(abc_cfg["sweep_seed"]),
                metrics={k: v for k, v in summary.items() if k != "data_version"},
                artifacts=[str(REPORT_MD)],
            )
        ]
    )
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunk", type=int, default=None)
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()
    _, raw = load_targets()
    n = int(raw["abc"]["n_candidates"])
    seed = int(raw["abc"]["sweep_seed"])
    if args.finalize:
        print(json.dumps(finalize(), indent=2, default=str))
        return 0
    account = float(raw["abc"].get("account_size") or 0) or None
    if args.chunk is not None:
        fp_chunk(WORLD_ROOT, str(OUT_DIR), seed, n, args.chunk, account_size=account)
        print(json.dumps({"chunk": args.chunk, "done": True}))
        return 0
    n_chunks = (n + CHUNK - 1) // CHUNK
    for i in range(n_chunks):
        fp_chunk(WORLD_ROOT, str(OUT_DIR), seed, n, i, account_size=account)
        print(f"chunk {i + 1}/{n_chunks} done ({dt.datetime.now():%H:%M:%S})", flush=True)
    print(json.dumps(finalize(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
