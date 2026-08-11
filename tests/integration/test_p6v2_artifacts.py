"""P4-P6 v2 rerun evidence (2026-08-10 amendment): the percentile-family
space's mystery gate and robustness numbers must exist as committed artifacts."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _j(rel: str) -> dict:
    p = REPO / rel
    assert p.exists(), f"missing evidence artifact {rel}"
    return json.loads(p.read_text())


def test_v2_mystery_gate_passed_on_18_dims() -> None:
    s = _j("experiments/p6v2/mystery_summary.json")
    assert s["gate_pass"] is True
    assert s["n_candidates"] == 16384
    assert s["n_accepted"] > 0
    assert len(s["dims_covered"]) == 18
    assert all(s["dims_covered"].values())  # v2 truth covered on every dim


def test_v2_robustness_front_page_numbers() -> None:
    dsr = _j("experiments/p6v2/robustness/dsr.json")
    pbo = _j("experiments/p6v2/robustness/pbo.json")
    assert 0.0 <= dsr["dsr"] <= 1.0
    assert dsr["n_trials"] == 16384
    assert 0.0 <= pbo["pbo"] <= 1.0


def test_v2_sweep_had_zero_survivors_and_both_families() -> None:
    s = _j("experiments/p4v2/sweep_summary.json")
    assert s["n_configs"] == 16384
    assert s["n_survivors"] == 0  # the honest discrimination, reproduced
    md = (REPO / "experiments/p4v2/analysis_addendum.md").read_text()
    assert "percentile" in md and "delta" in md


def test_v2_rerun_summary_labeled_synthetic() -> None:
    md = (REPO / "experiments/p6v2/rerun_summary.md").read_text()
    assert "SYNTHETIC" in md
    assert "No real-market conclusion" in md
