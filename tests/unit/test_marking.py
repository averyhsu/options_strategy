import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from options_strategy.data.marking import mark_chain
from options_strategy.data.schemas import ET
from options_strategy.pricing.black76 import price as b76

TS = dt.datetime(2026, 3, 6, 15, 59, tzinfo=ZoneInfo(ET))
EXPIRY = dt.date(2026, 3, 13)
F, DF, TAU, SIGMA = 5010.0, 0.9995, 7 / 365, 0.20


def _chain() -> tuple[pl.DataFrame, pl.DataFrame]:
    strikes = np.arange(4850.0, 5200.0, 25.0)
    rows = []
    for cp, w in (("C", 1), ("P", -1)):
        theo = b76(F, strikes, TAU, SIGMA, DF, cp=w)
        for k, m in zip(strikes, theo, strict=True):
            rows.append(
                {
                    "ts": TS,
                    "root": "SPXW",
                    "expiry_date": EXPIRY,
                    "am_pm_settle": "PM",
                    "strike": float(k),
                    "cp": cp,
                    "bid": max(round(m - 0.4, 2), 0.0),
                    "ask": round(m + 0.4, 2),
                    "bid_size": 10,
                    "ask_size": 10,
                    "last": round(m, 2),
                    "volume": 1,
                    "open_interest": 100,
                    "quote_condition": 0,
                }
            )
    quotes = pl.DataFrame(rows).with_columns(
        pl.col("ts").cast(pl.Datetime("us", ET)), pl.col("quote_condition").cast(pl.Int32)
    )
    forwards = pl.DataFrame(
        {
            "ts": [TS],
            "root": ["SPXW"],
            "expiry_date": [EXPIRY],
            "df_hat": [DF],
            "forward_hat": [F],
            "tau_years": [TAU],
        }
    ).with_columns(pl.col("ts").cast(pl.Datetime("us", ET)))
    return quotes, forwards


def test_sane_rows_mark_at_mid() -> None:
    quotes, forwards = _chain()
    marked = mark_chain(quotes, None, forwards)
    sane = marked.filter(pl.col("bid") > 0)
    assert sane.height > 0
    np.testing.assert_allclose(
        sane["mark"].to_numpy(), ((sane["bid"] + sane["ask"]) / 2).to_numpy()
    )
    assert not sane["marked_from_model"].any()


def test_flagged_row_gets_model_mark_between_its_own_quotes() -> None:
    quotes, forwards = _chain()
    victim_strike = 5000.0
    flags = pl.DataFrame(
        {
            "ts": [TS],
            "root": ["SPXW"],
            "expiry_date": [EXPIRY],
            "strike": [victim_strike],
            "cp": ["C"],
            "flags": [1],
        }
    ).with_columns(pl.col("ts").cast(pl.Datetime("us", ET)), pl.col("flags").cast(pl.Int32))
    marked = mark_chain(quotes, flags, forwards)
    row = marked.filter((pl.col("strike") == victim_strike) & (pl.col("cp") == "C")).row(
        0, named=True
    )
    assert row["marked_from_model"] is True
    theo = float(b76(F, victim_strike, TAU, SIGMA, DF, cp=1))
    assert abs(row["mark"] - theo) < 0.10  # interpolated through clean neighbors


def test_row_with_no_anchors_gets_null_mark() -> None:
    quotes, forwards = _chain()
    # Flag every call: no sane same-cp anchors remain -> null marks, no invention.
    calls = quotes.filter(pl.col("cp") == "C")
    flags = calls.select("ts", "root", "expiry_date", "strike", "cp").with_columns(
        flags=pl.lit(1, dtype=pl.Int32)
    )
    marked = mark_chain(quotes, flags, forwards)
    assert marked.filter(pl.col("cp") == "C")["mark"].is_null().all()
    assert marked.filter(pl.col("cp") == "P")["mark"].is_not_null().all()
