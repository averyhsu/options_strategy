"""Invariant §11.2 grep-lint: strategy modules must see markets only through
MarketView/BrokerLike — no data loaders, adapters, or drivers."""

import ast
from pathlib import Path

STRATEGY_DIR = Path(__file__).resolve().parents[2] / "src" / "options_strategy" / "strategy"

FORBIDDEN_MODULE_PREFIXES = (
    "options_strategy.data.adapters",
    "options_strategy.data.synthetic",
    "options_strategy.data.qa",
    "options_strategy.data.marking",
    "options_strategy.engine.backtest",
    "options_strategy.engine.track_a",
    "options_strategy.ledger",
    "polars.io",
)

FORBIDDEN_SOURCE_TOKENS = ("read_parquet", "scan_parquet", "read_csv", "open(")


def _imported_modules(tree: ast.AST) -> list[str]:
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def test_strategy_modules_import_no_loaders() -> None:
    files = sorted(STRATEGY_DIR.glob("*.py"))
    assert files, "strategy package not found"
    for f in files:
        src = f.read_text()
        mods = _imported_modules(ast.parse(src))
        for mod in mods:
            assert not any(mod.startswith(p) for p in FORBIDDEN_MODULE_PREFIXES), (
                f"{f.name} imports forbidden module {mod}"
            )
        for token in FORBIDDEN_SOURCE_TOKENS:
            assert token not in src, f"{f.name} contains forbidden token {token!r}"
