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


@pytest.fixture(scope="session")
def gap_world(tmp_path_factory) -> tuple[SyntheticWorldConfig, WorldPaths, dict]:
    """Two-week intraday world with a scripted -5% Monday gap (F4 rehearsal)."""
    from options_strategy.data.synthetic.config import ForcedEvent

    root = tmp_path_factory.mktemp("gapworld")
    cfg = SyntheticWorldConfig(
        name="gap-week-synthetic",
        seed=42,
        start=dt.date(2026, 3, 2),
        end=dt.date(2026, 3, 20),
        # 11 weeklies: on Friday morning the same-day expiry still occupies a
        # slot, and the 03-20 back leg must already be listed (PLAN §14).
        chain=ChainParams(n_weeklies=11, n_monthlies=1, near_band_pct=0.02, span_pct=0.06),
        snapshots=SnapshotSpec(
            eod=True,
            intraday_windows=((dt.date(2026, 3, 6), dt.date(2026, 3, 13)),),
            intraday_step_bars=5,
        ),
        forced_events=(ForcedEvent(session=dt.date(2026, 3, 9), gap_pct=-0.05, vol_mult=3.0),),
    )
    paths, summary = generate_world(cfg, root)
    return cfg, paths, summary


@pytest.fixture(scope="session")
def gap_world_qa(gap_world) -> QAResult:
    _, paths, _ = gap_world
    return run_qa(paths.root)
