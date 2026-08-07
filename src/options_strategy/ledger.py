"""Experiment ledger: append-only parquet of every run (PLAN §3.2, §9.4).

The row hash covers (kind, config_hash, git_sha, data_version, seed, metrics)
and excludes wall-clock fields, so identical config + seed + data_version
reproduce identical row hashes (invariant §11.7). If it isn't in the ledger,
it didn't happen.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

DEFAULT_LEDGER_PATH = Path("experiments/ledger.parquet")

LEDGER_SCHEMA: dict[str, pl.DataType] = {
    "run_id": pl.String(),
    "row_hash": pl.String(),
    "created_at": pl.String(),  # ISO-8601 UTC; deliberately excluded from row_hash
    "kind": pl.String(),  # worldgen | qa | backtest | sweep | match | report
    "config_hash": pl.String(),
    "git_sha": pl.String(),
    "data_version": pl.String(),
    "seed": pl.Int64(),
    "metrics": pl.String(),  # canonical JSON object
    "artifacts": pl.String(),  # canonical JSON list of repo-relative paths
}


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class LedgerRow:
    kind: str
    config_hash: str
    git_sha: str
    data_version: str
    seed: int
    metrics: dict[str, Any]
    artifacts: list[str] = field(default_factory=list)

    @property
    def row_hash(self) -> str:
        basis = _canon(
            {
                "kind": self.kind,
                "config_hash": self.config_hash,
                "git_sha": self.git_sha,
                "data_version": self.data_version,
                "seed": self.seed,
                "metrics": self.metrics,
            }
        )
        return hashlib.sha256(basis.encode("ascii")).hexdigest()

    @property
    def run_id(self) -> str:
        return f"{self.kind}-{self.row_hash[:12]}"

    def to_record(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "row_hash": self.row_hash,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "kind": self.kind,
            "config_hash": self.config_hash,
            "git_sha": self.git_sha,
            "data_version": self.data_version,
            "seed": self.seed,
            "metrics": _canon(self.metrics),
            "artifacts": _canon(self.artifacts),
        }


def current_git_sha(repo_root: str | Path | None = None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def append(rows: Iterable[LedgerRow], ledger_path: str | Path = DEFAULT_LEDGER_PATH) -> None:
    records = [r.to_record() for r in rows]
    if not records:
        return
    new = pl.DataFrame(records, schema=LEDGER_SCHEMA)
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        new = pl.concat([pl.read_parquet(path), new], how="vertical")
    tmp = path.with_suffix(".tmp.parquet")
    new.write_parquet(tmp)
    tmp.replace(path)


def read(ledger_path: str | Path = DEFAULT_LEDGER_PATH) -> pl.DataFrame:
    path = Path(ledger_path)
    if not path.exists():
        return pl.DataFrame(schema=LEDGER_SCHEMA)
    return pl.read_parquet(path)
