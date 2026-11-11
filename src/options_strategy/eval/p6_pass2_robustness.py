"""P6 Pass-2 robustness battery over the REAL decade (PLAN §10).

Runs the Pass-1 robustness components unchanged against the real-world P4
survivors: kept-config NAV matrix, walk-forward, deflated Sharpe, PBO (CSCV),
HISTORICAL stress windows (the six regime windows — real dates, not scripted
defects), block-bootstrap risk of ruin, and the fee battery.

Usage:  python -m options_strategy.eval.p6_pass2_robustness
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from options_strategy.eval.robustness import (
    deflated_sharpe,
    fee_sensitivity,
    kept_nav_matrix,
    pbo_cscv,
    risk_of_ruin,
    stress_windows,
    walk_forward,
)

WORLD = "data/raw/theta/decade_world"
SURVIVORS = "experiments/p4_pass2/survivors.parquet"
OUT = Path("experiments/p6_pass2/robustness")
N_TRIALS = 16384  # the full P4 sweep is the trial count for DSR

# real historical stress windows (the credit-check regimes + Dec-2018)
STRESS = [
    ("volmageddon-feb-2018", dt.date(2018, 1, 26), dt.date(2018, 3, 2)),
    ("dec-2018", dt.date(2018, 12, 1), dt.date(2018, 12, 31)),
    ("covid-mar-2020", dt.date(2020, 2, 21), dt.date(2020, 4, 3)),
    ("bear-2022", dt.date(2022, 1, 7), dt.date(2022, 10, 14)),
    ("vix-spike-aug-2024", dt.date(2024, 7, 26), dt.date(2024, 8, 23)),
    ("live-window-2026", dt.date(2026, 4, 1), dt.date(2026, 7, 30)),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kept_nav_matrix(WORLD, SURVIVORS, str(OUT))
    navs = pl.read_parquet(OUT / "kept_navs.parquet")

    (OUT / "wfo.json").write_text(json.dumps(walk_forward(navs), indent=2))
    (OUT / "dsr.json").write_text(json.dumps(deflated_sharpe(navs, N_TRIALS), indent=2))
    (OUT / "pbo.json").write_text(json.dumps(pbo_cscv(navs), indent=2))
    (OUT / "stress_windows.json").write_text(json.dumps(stress_windows(navs, STRESS), indent=2))
    (OUT / "ruin.json").write_text(
        json.dumps(risk_of_ruin(str(OUT / "kept_cycles.parquet")), indent=2)
    )
    (OUT / "fees.json").write_text(json.dumps(fee_sensitivity(WORLD, SURVIVORS), indent=2))
    print(
        json.dumps(
            {
                "dsr": json.loads((OUT / "dsr.json").read_text()),
                "pbo": json.loads((OUT / "pbo.json").read_text()),
                "n_stress_windows": len(STRESS),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
