"""Internal data schemas (PLAN §4.1). All vendors adapt into these; the
synthetic generator emits them natively. Timestamps are tz-aware ET and label
the bar START (see ASSUMPTIONS.md).
"""

from __future__ import annotations

import polars as pl

ET = "America/New_York"

TS_ET = pl.Datetime("us", ET)

OPTION_QUOTES_SCHEMA: dict[str, pl.DataType] = {
    "ts": TS_ET,
    "root": pl.String(),  # SPX | SPXW
    "expiry_date": pl.Date(),
    "am_pm_settle": pl.String(),  # AM | PM
    "strike": pl.Float64(),
    "cp": pl.String(),  # C | P
    "bid": pl.Float64(),
    "ask": pl.Float64(),
    "bid_size": pl.Int64(),
    "ask_size": pl.Int64(),
    "last": pl.Float64(),
    "volume": pl.Int64(),
    "open_interest": pl.Int64(),  # EOD field; never used intraday (PLAN §14)
    "quote_condition": pl.Int32(),  # 0 = normal; defect codes per synthetic.microstructure
}

UNDERLYING_BARS_SCHEMA: dict[str, pl.DataType] = {
    "ts": TS_ET,
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
}

RATES_SCHEMA: dict[str, pl.DataType] = {
    "date": pl.Date(),
    "tenor_days": pl.Int64(),
    "rate": pl.Float64(),  # continuously-compounded zero rate, ACT/365
}

SESSIONS_SCHEMA: dict[str, pl.DataType] = {
    "session": pl.Date(),
    "open_et": TS_ET,
    "close_et": TS_ET,
    "early_close": pl.Boolean(),
}

EXPIRIES_SCHEMA: dict[str, pl.DataType] = {
    "expiry_date": pl.Date(),
    "root": pl.String(),  # SPX | SPXW
    "settlement": pl.String(),  # AM | PM
}

SETTLEMENTS_SCHEMA: dict[str, pl.DataType] = {
    "expiry_date": pl.Date(),
    "root": pl.String(),
    "settlement": pl.String(),
    "value": pl.Float64(),  # official settlement print (synthetic: from the index path)
}


def validate_schema(df: pl.DataFrame, schema: dict[str, pl.DataType], name: str) -> pl.DataFrame:
    """Raise if df's columns/dtypes deviate from the declared schema."""
    expected = list(schema.items())
    actual = list(df.schema.items())
    if actual != expected:
        raise ValueError(f"{name}: schema mismatch.\n  expected: {expected}\n  actual:   {actual}")
    return df
