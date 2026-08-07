"""Config canonicalization, hashing, and YAML loading.

Every run is identified by the sha256 of its config's canonical JSON (PLAN §3.2):
identical config + seed + data_version must yield identical ledger row hashes,
so canonicalization is key-sorted, separator-fixed, ASCII-only JSON.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel


def canonical_json(model: BaseModel) -> str:
    payload = model.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_hash(model: BaseModel) -> str:
    return hashlib.sha256(canonical_json(model).encode("ascii")).hexdigest()


def short_hash(model: BaseModel) -> str:
    return config_hash(model)[:12]


def load_config[M: BaseModel](path: str | Path, model_cls: type[M]) -> M:
    """Load a YAML file into a pydantic model (strict: unknown keys are errors)."""
    with open(path, "rb") as fh:
        raw = yaml.safe_load(fh)
    return model_cls.model_validate(raw if raw is not None else {})
