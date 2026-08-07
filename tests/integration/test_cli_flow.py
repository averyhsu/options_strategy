import textwrap

import polars as pl

from options_strategy import cli
from options_strategy.ledger import read as ledger_read

TINY_YAML = textwrap.dedent(
    """
    name: cli-tiny-synthetic
    seed: 5
    start: 2026-04-06
    end: 2026-04-10
    chain: {n_weeklies: 3, n_monthlies: 1, near_band_pct: 0.02, span_pct: 0.05}
    snapshots: {eod: true, intraday_windows: []}
    """
)


def test_worldgen_then_qa_via_cli_with_ledger(tmp_path) -> None:
    cfg_path = tmp_path / "world.yaml"
    cfg_path.write_text(TINY_YAML)
    out = tmp_path / "worlds"
    ledger_path = tmp_path / "ledger.parquet"

    rc = cli.main(
        ["worldgen", "--config", str(cfg_path), "--out", str(out), "--ledger", str(ledger_path)]
    )
    assert rc == 0
    world_root = out / "cli-tiny-synthetic"
    assert (world_root / "manifest.json").exists()

    rc = cli.main(["qa", "--world", str(world_root), "--ledger", str(ledger_path)])
    assert rc == 0

    rows = ledger_read(ledger_path)
    assert rows.height == 2
    assert set(rows["kind"].to_list()) == {"worldgen", "qa"}
    assert rows.filter(pl.col("kind") == "qa")["data_version"].item().startswith("synthetic-")
