"""Final download verification: per-file sha256 + parquet readability across
every vendor store, MANIFEST.md with named gaps, and the DOWNLOADS_COMPLETE
marker — written ONLY if every check passes.

Usage:  python -m options_strategy.data.vendors.theta_verify
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl

MANIFEST_ROOT = Path("data/raw/theta")
STORES: dict[str, tuple[Path, int]] = {
    # store name -> (glob root, expected parquet count; -1 = no fixed count)
    "credit_check_slice (51 dates x 3 snapshots)": (
        Path("data/raw/thetadata/credit_check_slice/quotes"),
        51,
    ),
    "exit7_snapshots (20 exit dates)": (Path("data/raw/thetadata/exit7_snapshots/quotes"), 20),
    "eod_preview raw (104 sessions)": (Path("data/raw/theta/eod_preview/raw"), 104),
    "bars15 decade (2665 sessions)": (Path("data/raw/theta/bars15/raw"), 2665),
    "ticks touch-weeks (214 weeks)": (Path("data/raw/theta/ticks/weeks"), 214),
}
NAMED_GAPS = [
    "ticks week=2021-06-18: contract-day SPXW 2021-06-25 4240C on 2021-06-21 "
    "missing — vendor-side 500 (ArrayIndexOutOfBoundsException) on every "
    "attempt across three runs; 45 of 46 expected contract-days present.",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify() -> tuple[bool, str]:
    lines = [
        "# ThetaData paid-month downloads — verification manifest",
        "",
        f"Generated {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')} by "
        "theta_verify.py. Licensed vendor data: this directory is gitignored; "
        "only this manifest's COPY in experiments/ is committed.",
        "",
        "## Named gaps",
        "",
        *[f"- {g}" for g in NAMED_GAPS],
        "",
    ]
    all_ok = True
    for name, (root, expected) in STORES.items():
        files = sorted(root.glob("*.parquet"))
        count_ok = expected < 0 or len(files) == expected
        readable = 0
        broken: list[str] = []
        lines += [
            f"## {name}",
            "",
            f"- path: `{root}`",
            f"- files: {len(files)} (expected {expected}) {'OK' if count_ok else '** MISMATCH **'}",
        ]
        if not count_ok:
            all_ok = False
        entries = []
        total_bytes = 0
        for f in files:
            try:
                pl.read_parquet_schema(f)
                readable += 1
            except Exception as e:  # unreadable footer/corruption
                broken.append(f"{f.name}: {e}")
            size = f.stat().st_size
            total_bytes += size
            entries.append(f"| {f.name} | {size} | {sha256_file(f)} |")
        lines += [
            f"- readable: {readable}/{len(files)}"
            f" {'OK' if not broken else '** BROKEN: ' + '; '.join(broken) + ' **'}",
            f"- bytes: {total_bytes:,}",
            "",
            "| file | bytes | sha256 |",
            "|---|---|---|",
            *entries,
            "",
        ]
        if broken:
            all_ok = False
    return all_ok, "\n".join(lines)


def main() -> int:
    ok, manifest = verify()
    out = MANIFEST_ROOT / "MANIFEST.md"
    out.write_text(manifest)
    committed_copy = Path("experiments/theta_downloads/MANIFEST.md")
    committed_copy.parent.mkdir(parents=True, exist_ok=True)
    committed_copy.write_text(manifest)
    if ok:
        (MANIFEST_ROOT / "DOWNLOADS_COMPLETE").write_text(
            dt.datetime.now(dt.UTC).isoformat(timespec="seconds") + "\n"
        )
    print(json.dumps({"all_ok": ok, "manifest": str(out), "downloads_complete_written": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
