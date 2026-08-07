import polars as pl

from options_strategy.ledger import LEDGER_SCHEMA, LedgerRow, append, read


def _row(**overrides) -> LedgerRow:
    base = {
        "kind": "worldgen",
        "config_hash": "c" * 64,
        "git_sha": "a" * 40,
        "data_version": "synthetic-abc123",
        "seed": 42,
        "metrics": {"n_rows": 100, "qa_clean": True},
        "artifacts": ["data/synthetic/worlds/x/manifest.json"],
    }
    base.update(overrides)
    return LedgerRow(**base)


def test_row_hash_is_deterministic_and_excludes_wall_clock() -> None:
    a, b = _row(), _row()
    assert a.row_hash == b.row_hash
    # created_at differs between records (or not), but never feeds the hash:
    ra, rb = a.to_record(), b.to_record()
    assert ra["row_hash"] == rb["row_hash"]


def test_row_hash_changes_with_inputs() -> None:
    base = _row().row_hash
    assert _row(seed=43).row_hash != base
    assert _row(metrics={"n_rows": 101}).row_hash != base
    assert _row(data_version="synthetic-def456").row_hash != base


def test_run_id_carries_kind_and_hash_prefix() -> None:
    r = _row()
    assert r.run_id == f"worldgen-{r.row_hash[:12]}"


def test_append_and_read_round_trip(tmp_path) -> None:
    path = tmp_path / "ledger.parquet"
    append([_row()], path)
    append([_row(seed=43), _row(seed=44)], path)
    df = read(path)
    assert df.height == 3
    assert dict(df.schema) == dict(pl.Schema(LEDGER_SCHEMA))
    assert df["seed"].to_list() == [42, 43, 44]


def test_read_missing_ledger_is_empty_with_schema(tmp_path) -> None:
    df = read(tmp_path / "nope.parquet")
    assert df.height == 0
    assert dict(df.schema) == dict(pl.Schema(LEDGER_SCHEMA))
