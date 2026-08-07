import datetime as dt
import hashlib
import shutil
from pathlib import Path

import polars as pl
import pytest

from options_strategy.data.qa import run_qa
from options_strategy.data.schemas import (
    EXPIRIES_SCHEMA,
    OPTION_QUOTES_SCHEMA,
    RATES_SCHEMA,
    SESSIONS_SCHEMA,
    SETTLEMENTS_SCHEMA,
    UNDERLYING_BARS_SCHEMA,
    validate_schema,
)
from options_strategy.data.synthetic.config import (
    ChainParams,
    MicrostructureParams,
    SnapshotSpec,
    SyntheticWorldConfig,
)
from options_strategy.data.synthetic.world import WorldPaths, generate_world, settle_datetime

TINY_KW = {
    "seed": 11,
    "start": dt.date(2026, 3, 2),
    "end": dt.date(2026, 3, 20),
    "chain": ChainParams(n_weeklies=3, n_monthlies=1, near_band_pct=0.02, span_pct=0.05),
    "snapshots": SnapshotSpec(
        eod=True, intraday_windows=((dt.date(2026, 3, 10), dt.date(2026, 3, 10)),)
    ),
}


@pytest.fixture(scope="module")
def clean_world(tmp_path_factory) -> tuple[SyntheticWorldConfig, WorldPaths, dict]:
    root = tmp_path_factory.mktemp("worlds")
    cfg = SyntheticWorldConfig(name="tiny-clean-synthetic", **TINY_KW)
    paths, summary = generate_world(cfg, root)
    return cfg, paths, summary


def test_all_outputs_conform_to_schemas(clean_world) -> None:
    _, paths, _ = clean_world
    for f in paths.quote_files():
        validate_schema(pl.read_parquet(f), OPTION_QUOTES_SCHEMA, f.name)
    validate_schema(pl.read_parquet(paths.underlying), UNDERLYING_BARS_SCHEMA, "underlying")
    validate_schema(pl.read_parquet(paths.sessions), SESSIONS_SCHEMA, "sessions")
    validate_schema(pl.read_parquet(paths.expiries), EXPIRIES_SCHEMA, "expiries")
    validate_schema(pl.read_parquet(paths.rates), RATES_SCHEMA, "rates")
    validate_schema(pl.read_parquet(paths.settlements), SETTLEMENTS_SCHEMA, "settlements")


def test_quotes_only_for_listed_unexpired_options(clean_world) -> None:
    _, paths, _ = clean_world
    listed = set(pl.read_parquet(paths.expiries).select("expiry_date", "root").iter_rows())
    for f in paths.quote_files():
        q = pl.read_parquet(f)
        assert set(q.select("expiry_date", "root").unique().iter_rows()) <= listed
        naive = q.with_columns(pl.col("ts").dt.replace_time_zone(None))
        for expiry, settlement, ts_max in (
            naive.group_by("expiry_date", "am_pm_settle").agg(pl.col("ts").max()).iter_rows()
        ):
            assert ts_max < settle_datetime(expiry, settlement)


def test_settlements_match_path_prints_exactly(clean_world) -> None:
    _, paths, _ = clean_world
    bars = pl.read_parquet(paths.underlying).with_columns(session=pl.col("ts").dt.date())
    daily = bars.group_by("session", maintain_order=True).agg(
        pl.col("open").first().alias("day_open"),
        pl.col("close").last().alias("day_close"),
    )
    lookup = {r["session"]: r for r in daily.iter_rows(named=True)}
    settlements = pl.read_parquet(paths.settlements)
    assert settlements.height > 0
    for row in settlements.iter_rows(named=True):
        day = lookup[row["expiry_date"]]
        expected = day["day_open"] if row["settlement"] == "AM" else day["day_close"]
        assert row["value"] == expected  # exact, to the bit


def test_qa_is_clean_on_pristine_world(clean_world) -> None:
    _, paths, _ = clean_world
    result = run_qa(paths.root)
    assert result.summary["truth"]["n_compared"] > 0
    assert result.clean, result.summary
    assert result.report_path.exists()
    assert "SYNTHETIC" in result.report_path.read_text()


def test_qa_clean_with_injected_defects_and_all_detected(tmp_path) -> None:
    cfg = SyntheticWorldConfig(
        name="tiny-defect-synthetic",
        **{
            **TINY_KW,
            "micro": MicrostructureParams(stale_rate=0.05, crossed_rate=0.003, locked_rate=0.003),
        },
    )
    paths, summary = generate_world(cfg, tmp_path)
    assert summary["n_injected_defects"] > 0
    result = run_qa(paths.root)
    assert result.summary["n_flagged_rows"] > 0
    assert result.summary["unexpected"]["sanity_rows"] == 0
    assert result.summary["unexpected"]["structure_rows"] == 0
    assert result.summary["unexpected"]["parity_bad"] == 0
    assert result.summary["missed_injected"]["crossed_locked_rows"] == 0
    assert result.summary["missed_injected"]["stale_episodes"] == 0
    # Frozen windows really did corrupt their snapshots (raw violations exist),
    # and every one of them was attributed to an injected defect:
    assert result.summary["n_parity_bad"] > 0 or any(
        v > 0 for v in result.summary["structure_violations"].values()
    )
    assert result.clean, result.summary


def test_qa_fails_on_uninjected_corruption(clean_world, tmp_path) -> None:
    _, paths, _ = clean_world
    bad_root = tmp_path / "corrupted-synthetic"
    shutil.copytree(paths.root, bad_root)
    if (bad_root / "qa").exists():
        shutil.rmtree(bad_root / "qa")
    target = sorted((bad_root / "option_quotes").glob("date=*.parquet"))[0]
    df = pl.read_parquet(target)
    df = df.with_columns(
        bid=pl.when(pl.int_range(pl.len()) < 25).then(pl.col("ask") + 0.35).otherwise(pl.col("bid"))
    )
    df.write_parquet(target)
    result = run_qa(bad_root)
    assert not result.clean
    assert result.summary["unexpected"]["sanity_rows"] >= 25


def _tree_hashes(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_regeneration_is_bit_identical(clean_world, tmp_path) -> None:
    cfg, paths, _ = clean_world
    paths2, _ = generate_world(cfg, tmp_path)
    a = _tree_hashes(paths.root)
    b = _tree_hashes(paths2.root)
    a = {k: v for k, v in a.items() if not k.startswith("qa/")}
    assert a == b
