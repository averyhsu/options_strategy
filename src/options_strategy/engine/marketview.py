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
        *,
        daily_history: pl.DataFrame | None = None,  # completed sessions BEFORE today
        today_open: float | None = None,
        today_high: float | None = None,
        today_low: float | None = None,
        is_last_session_of_week: bool = False,
        is_second_last_session_of_week: bool = False,
        next_session: dt.date | None = None,
    ):
        self._ts = ts
        self._spot = spot
        self._chain = chain
        self._forwards = forwards
        self._session_date = session_date
        self._is_last = is_last_bar_of_session
        self._daily_history = daily_history
        self.today_open = today_open if today_open is not None else spot
        self.today_high = today_high if today_high is not None else spot
        self.today_low = today_low if today_low is not None else spot
        self.is_last_session_of_week = is_last_session_of_week
        self.is_second_last_session_of_week = is_second_last_session_of_week
        self.next_session = next_session
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

    def daily_history(self) -> pl.DataFrame:
        """Completed daily candles strictly before today (no-lookahead)."""
        if self._daily_history is None:
            return pl.DataFrame(
                schema={
                    "session": pl.Date(),
                    "open": pl.Float64(),
                    "high": pl.Float64(),
                    "low": pl.Float64(),
                    "close": pl.Float64(),
                }
            )
        return self._daily_history

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
            c = self._chain
            idx: dict[OptionKey, LegQuote] = {}
            for root, expiry, strike, cp, bid, ask, bsz, asz, flags in zip(
                c["root"].to_list(),
                c["expiry_date"].to_list(),
                c["strike"].to_list(),
                c["cp"].to_list(),
                c["bid"].to_list(),
                c["ask"].to_list(),
                c["bid_size"].to_list(),
                c["ask_size"].to_list(),
                c["flags"].to_list(),
                strict=True,
            ):
                idx[OptionKey(root, expiry, strike, cp)] = LegQuote(
                    bid=bid, ask=ask, bid_size=bsz, ask_size=asz, sane=(flags == 0)
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
