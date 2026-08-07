import datetime as dt

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from options_strategy.config import canonical_json, config_hash, load_config, short_hash


class Cfg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    beta: int = 2
    alpha: str = "x"
    when: dt.date = dt.date(2026, 1, 2)


def test_canonical_json_is_key_sorted() -> None:
    assert canonical_json(Cfg()) == '{"alpha":"x","beta":2,"when":"2026-01-02"}'


def test_hash_stable_across_construction_order() -> None:
    assert config_hash(Cfg(beta=2, alpha="x")) == config_hash(Cfg(alpha="x", beta=2))


def test_hash_changes_with_any_field() -> None:
    base = config_hash(Cfg())
    assert config_hash(Cfg(beta=3)) != base
    assert config_hash(Cfg(alpha="y")) != base
    assert config_hash(Cfg(when=dt.date(2026, 1, 3))) != base


def test_short_hash_is_prefix() -> None:
    assert config_hash(Cfg()).startswith(short_hash(Cfg()))
    assert len(short_hash(Cfg())) == 12


def test_load_config_round_trip(tmp_path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("alpha: y\nbeta: 7\n")
    cfg = load_config(p, Cfg)
    assert cfg == Cfg(alpha="y", beta=7)


def test_load_config_rejects_unknown_keys(tmp_path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text("alpha: y\nbogus: 1\n")
    with pytest.raises(ValidationError):
        load_config(p, Cfg)
