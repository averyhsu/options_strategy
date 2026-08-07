"""Tradeable instruments: SPX/SPXW options and a synthetic delta-one index
unit (used by golden tests and the optional delta-hedge defense action).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class OptionKey:
    root: str  # SPX | SPXW
    expiry: dt.date
    strike: float
    cp: str  # C | P

    def __post_init__(self) -> None:
        if self.root not in ("SPX", "SPXW"):
            raise ValueError(f"bad root {self.root}")
        if self.cp not in ("C", "P"):
            raise ValueError(f"bad cp {self.cp}")

    @property
    def settlement(self) -> str:
        return "PM" if self.root == "SPXW" else "AM"


@dataclass(frozen=True)
class IndexUnit:
    """One unit of the cash index (value = index level in dollars)."""

    symbol: str = "SPX_INDEX"


INDEX = IndexUnit()

Instrument = OptionKey | IndexUnit
