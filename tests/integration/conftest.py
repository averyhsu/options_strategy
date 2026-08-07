import datetime as dt

import pytest

from options_strategy.data.qa import QAResult, run_qa
from options_strategy.data.synthetic.config import ChainParams, SnapshotSpec, SyntheticWorldConfig
from options_strategy.data.synthetic.world import WorldPaths, generate_world


@pytest.fixture(scope="session")
def tiny_world_kwargs() -> dict:
    return {
        "seed": 11,
        "start": dt.date(2026, 3, 2),
        "end": dt.date(2026, 3, 20),
        "chain": ChainParams(n_weeklies=8, n_monthlies=1, near_band_pct=0.02, span_pct=0.05),
        "snapshots": SnapshotSpec(
            eod=True, intraday_windows=((dt.date(2026, 3, 10), dt.date(2026, 3, 10)),)
        ),
    }


@pytest.fixture(scope="session")
def clean_world(
    tmp_path_factory, tiny_world_kwargs
) -> tuple[SyntheticWorldConfig, WorldPaths, dict]:
    root = tmp_path_factory.mktemp("worlds")
    cfg = SyntheticWorldConfig(name="tiny-clean-synthetic", **tiny_world_kwargs)
    paths, summary = generate_world(cfg, root)
    return cfg, paths, summary


@pytest.fixture(scope="session")
def clean_world_qa(clean_world) -> QAResult:
    _, paths, _ = clean_world
    return run_qa(paths.root)
