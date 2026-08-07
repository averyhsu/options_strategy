"""Settlement values and expiry cash conversion (PLAN §6, §14).

European cash-settled only — there are NO exercise/assignment mechanics.
SPXW is PM-settled (4pm closing print); SPX monthlies are AM-settled (SET,
computed from Friday opening prints). Mixing these corrupts expiry P&L, so
lookups are keyed by (root, expiry_date) against the dataset's settlement
table and refuse to guess when a value is missing.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import polars as pl


class SettlementTable:
    def __init__(self, frame: pl.DataFrame):
        self._values: dict[tuple[str, dt.date], tuple[str, float]] = {
            (r["root"], r["expiry_date"]): (r["settlement"], r["value"])
            for r in frame.iter_rows(named=True)
        }

    @classmethod
    def from_parquet(cls, path: str | Path) -> SettlementTable:
        return cls(pl.read_parquet(path))

    def value(self, root: str, expiry: dt.date) -> float:
        key = (root, expiry)
        if key not in self._values:
            raise KeyError(
                f"no official settlement value for {root} {expiry} — refusing to guess "
                "(PLAN §4.1 settlement_values)"
            )
        return self._values[key][1]

    def settlement_kind(self, root: str, expiry: dt.date) -> str:
        key = (root, expiry)
        if key not in self._values:
            raise KeyError(f"no settlement row for {root} {expiry}")
        return self._values[key][0]


def settlement_intrinsic(
    cp: np.ndarray | str, strike: np.ndarray | float, settle_value: np.ndarray | float
) -> np.ndarray:
    """Cash value in index points of an expiring option: max(w*(S_settle-K), 0)."""
    from options_strategy.pricing.black76 import cp_sign

    w = cp_sign(cp) if not isinstance(cp, int) else cp
    k = np.asarray(strike, dtype=np.float64)
    s = np.asarray(settle_value, dtype=np.float64)
    return np.maximum(np.asarray(w, dtype=np.float64) * (s - k), 0.0)
