"""P6 acceptance artifacts (PLAN §12 P6, Pass-1): the mystery gate and the
front-page numbers must exist as committed, machine-readable evidence."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _j(rel: str) -> dict:
    p = REPO / rel
    assert p.exists(), f"missing evidence artifact {rel}"
    return json.loads(p.read_text())


def test_mystery_gate_passed() -> None:
    s = _j("experiments/p6/mystery_summary.json")
    assert s["gate_pass"] is True
    assert s["n_accepted"] > 0
    assert s["n_hard_pass_dd_dates"] > 0
    assert s["n_candidates"] == 16384


def test_front_page_metrics_exist_and_are_sane() -> None:
    dsr = _j("experiments/p6/robustness/dsr.json")
    pbo = _j("experiments/p6/robustness/pbo.json")
    assert 0.0 <= dsr["dsr"] <= 1.0
    assert dsr["n_trials"] == 16384
    assert 0.0 <= pbo["pbo"] <= 1.0
    assert pbo["n_splits"] >= 100


def test_final_report_is_labeled_synthetic() -> None:
    report = (REPO / "FINAL_REPORT_SYNTHETIC.md").read_text()
    assert "SYNTHETIC DATA ONLY" in report
    assert "Deflated Sharpe Ratio" in report and "PBO" in report
    assert "investment advice" in report
