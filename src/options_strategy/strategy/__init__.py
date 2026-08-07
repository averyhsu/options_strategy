"""Strategy family (PLAN §8): regime filter, double-diagonal builder,
EV-gated entries, defense policy DSL, weekly cycle, Track-A compilation.

Strategy code sees markets ONLY through the MarketView facade (invariant
§11.2) — importing data loaders from here is forbidden and lint-tested.
"""
