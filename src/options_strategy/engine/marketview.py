"""MarketView facade (PLAN §7.1, §11.2): the ONLY market access strategy code
gets. It is constructed from the current bar's snapshot alone — nothing about
the future exists on this object, and strategies must not import data loaders.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from options_strategy.engine.fills import LegQuote
from options_strategy.engine.instruments import OptionKey


class MarketView:
    def __init__(
        self,
        ts: dt.datetime,
        spot: float,
        chain: pl.DataFrame,  # this bar's quotes with `flags` and mid/half
        forwards: pl.DataFrame,  # this bar's parity fits
        session_date: dt.date,
        is_last_bar_of_session: bool,
    ):
        self._ts = ts
        self._spot = spot
        self._chain = chain
        self._forwards = forwards
        self._session_date = session_date
        self._is_last = is_last_bar_of_session
        self._quote_index: dict[OptionKey, LegQuote] | None = None

    @property
    def ts(self) -> dt.datetime:
        return self._ts

    @property
    def spot(self) -> float:
        return self._spot

    @property
    def session_date(self) -> dt.date:
        return self._session_date

    @property
    def is_last_bar_of_session(self) -> bool:
        return self._is_last

    def chain(
        self, root: str | None = None, expiry: dt.date | None = None, sane_only: bool = True
    ) -> pl.DataFrame:
        df = self._chain
        if root is not None:
            df = df.filter(pl.col("root") == root)
        if expiry is not None:
            df = df.filter(pl.col("expiry_date") == expiry)
        if sane_only:
            df = df.filter(pl.col("flags") == 0)
        return df

    def expiries(self) -> list[tuple[dt.date, str, str]]:
        rows = (
            self._chain.select("expiry_date", "root", "am_pm_settle")
            .unique()
            .sort(["expiry_date", "root"])
        )
        return [tuple(r) for r in rows.iter_rows()]

    def quotes(self) -> dict[OptionKey, LegQuote]:
        if self._quote_index is None:
            idx: dict[OptionKey, LegQuote] = {}
            for r in self._chain.iter_rows(named=True):
                key = OptionKey(r["root"], r["expiry_date"], r["strike"], r["cp"])
                idx[key] = LegQuote(
                    bid=r["bid"],
                    ask=r["ask"],
                    bid_size=r["bid_size"],
                    ask_size=r["ask_size"],
                    sane=(r["flags"] == 0),
                )
            self._quote_index = idx
        return self._quote_index

    def quote(self, key: OptionKey) -> LegQuote | None:
        return self.quotes().get(key)

    def forward(self, root: str, expiry: dt.date) -> tuple[float, float, float] | None:
        """(forward, df, tau_years) from the parity fit, if one exists here."""
        fit = self._forwards.filter((pl.col("root") == root) & (pl.col("expiry_date") == expiry))
        if fit.height != 1 or not fit["parity_ok"][0]:
            return None
        return (
            float(fit["forward_hat"][0]),
            float(fit["df_hat"][0]),
            float(fit["tau_years"][0]),
        )
