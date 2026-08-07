from pathlib import Path

from options_strategy.config import load_config
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.fees import FeeConfig

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_fee_is_author_number() -> None:
    fees = FeeConfig()
    assert abs(fees.per_contract_leg - 1.60) < 1e-12


def test_fill_fee_scales_with_contracts_and_legs() -> None:
    fees = FeeConfig()
    assert abs(fees.fill_fee(1, n_legs=4) - 6.40) < 1e-12
    assert abs(fees.fill_fee(3, n_legs=4) - 19.20) < 1e-12
    assert abs(fees.fill_fee(-2, n_legs=1) - 3.20) < 1e-12  # sign-insensitive


def test_sensitivity_multiplier() -> None:
    fees = FeeConfig(multiplier=3.0)
    assert abs(fees.per_contract_leg - 4.80) < 1e-12


def test_base_yaml_reproduces_author_numbers() -> None:
    """PLAN §12 P2 AC: the committed config reproduces ~$1.60/leg all-in."""
    cfg = load_config(REPO_ROOT / "configs" / "base.yaml", EngineConfig)
    assert abs(cfg.fees.per_contract_leg - 1.60) < 1e-12
    assert cfg.account_size == 100_000.0
    assert cfg.fill_model.value == "conservative"
