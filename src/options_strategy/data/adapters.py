"""Dataset adapters -> internal schemas (PLAN §4).

The synthetic world already writes the internal schemas; its adapter is a thin
path-aware reader. Real vendor adapters are built ONLY when purchased data
actually lands in data/raw/ (ASSUMPTIONS.md), so the vendor entry here is an
explicit stub that names the contract instead of guessing formats.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from options_strategy.data.synthetic.world import WorldPaths


class SyntheticWorldAdapter:
    """Reads a generated synthetic world as the internal dataset contract."""

    def __init__(self, root: str | Path):
        self.paths = WorldPaths(Path(root))
        if not self.paths.manifest.exists():
            raise FileNotFoundError(f"not a dataset root (no manifest): {root}")
        self.manifest = json.loads(self.paths.manifest.read_text())

    @property
    def data_version(self) -> str:
        return self.manifest["data_version"]

    @property
    def label(self) -> str:
        return self.manifest["label"]

    def sessions(self) -> pl.DataFrame:
        return pl.read_parquet(self.paths.sessions)

    def expiries(self) -> pl.DataFrame:
        return pl.read_parquet(self.paths.expiries)

    def underlying_bars(self) -> pl.DataFrame:
        return pl.read_parquet(self.paths.underlying)

    def rates(self) -> pl.DataFrame:
        return pl.read_parquet(self.paths.rates)

    def settlements(self) -> pl.DataFrame:
        return pl.read_parquet(self.paths.settlements)

    def option_quotes(self, session: dt.date) -> pl.DataFrame:
        f = self.paths.quotes_dir / f"date={session.isoformat()}.parquet"
        if not f.exists():
            raise FileNotFoundError(f"no quotes for session {session}")
        return pl.read_parquet(f)

    def quality_flags(self) -> pl.DataFrame:
        f = self.paths.qa_dir / "quality_flags.parquet"
        if not f.exists():
            raise FileNotFoundError(
                "quality_flags.parquet missing — run `options_strategy qa` on this dataset "
                "before using it (PLAN §4.2: the engine refuses un-QA'd data)"
            )
        return pl.read_parquet(f)

    def forwards_extracted(self) -> pl.DataFrame:
        f = self.paths.qa_dir / "forwards_extracted.parquet"
        if not f.exists():
            raise FileNotFoundError(
                "forwards_extracted.parquet missing — run `options_strategy qa` first"
            )
        return pl.read_parquet(f)


class VendorAdapterStub:
    """Placeholder for the Pass-2 vendor adapter (Theta Data / CBOE DataShop /
    Polygon — vendor TBD by the user's purchase). Raises on any use."""

    VENDORS = ("theta_data", "cboe_datashop", "polygon")

    def __init__(self, vendor: str, raw_root: str | Path = "data/raw"):
        raise NotImplementedError(
            f"vendor adapter '{vendor}' is built in Pass 2, when purchased data lands in "
            f"{raw_root}/ (PLAN §12.0 pass structure; ASSUMPTIONS.md 2026-08-06). "
            f"Known vendor targets: {', '.join(self.VENDORS)}."
        )
