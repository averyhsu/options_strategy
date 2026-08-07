"""Whole-world precompute for the coarse sweep (PLAN §9.1).

Everything config-INDEPENDENT is computed once: per-session SPXW chain sides
as sorted numpy arrays with IVs and undiscounted |delta| (one giant vectorized
solve across all rows), parity forwards, settlement values, entry-session
flags, and regime gate tables per (ema_len, hysteresis) combo. The fast runner
then evaluates thousands of configs against these structures without touching
polars or the IV solver again.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.pricing.greeks import greeks
from options_strategy.pricing.iv import implied_vol
from options_strategy.strategy.regime import RegimeConfig, regime_frame

_KEY = ["ts", "root", "expiry_date", "strike", "cp"]


@dataclass
class Side:
    strikes: np.ndarray  # sorted, sane two-sided rows only
    bid: np.ndarray
    ask: np.ndarray
    mid: np.ndarray
    bid_size: np.ndarray
    ask_size: np.ndarray
    iv: np.ndarray  # NaN where unsolvable
    delta_abs: np.ndarray  # undiscounted |N(d1)|-style; NaN with iv


@dataclass
class SessionData:
    session: dt.date
    expiries: list[dt.date]  # SPXW expiries visible this session (sorted)
    sides: dict[tuple[dt.date, str], Side]
    forwards: dict[dt.date, tuple[float, float, float]]  # expiry -> (F, DF, tau)
    close: float


@dataclass
class WorldCache:
    sessions: list[dt.date]
    by_session: dict[dt.date, SessionData]
    settlements: dict[dt.date, float]  # SPXW expiry -> official PM print
    entry_flags: list[bool]  # weekday==4 or last of ISO week
    regime_allow: dict[tuple[int, float], dict[dt.date, tuple[str, str]]] = field(
        default_factory=dict
    )  # (ema_len, h) -> session -> (state, event)


def build_cache(
    adapter: SyntheticWorldAdapter, ema_hyst_combos: list[tuple[int, float]]
) -> WorldCache:
    sessions_df = adapter.sessions()
    session_list: list[dt.date] = sessions_df["session"].to_list()
    n = len(session_list)
    iso = [(d.isocalendar().year, d.isocalendar().week) for d in session_list]
    entry_flags = [
        session_list[i].weekday() == 4 or i == n - 1 or iso[i + 1] != iso[i] for i in range(n)
    ]

    flags_all = adapter.quality_flags()
    forwards_all = adapter.forwards_extracted().filter(pl.col("root") == "SPXW")

    frames = []
    for session in session_list:
        q = adapter.option_quotes(session)
        q = q.filter(pl.col("root") == "SPXW")
        eod_ts = q["ts"].max()
        frames.append(q.filter(pl.col("ts") == eod_ts))
    big = pl.concat(frames)
    big = big.join(flags_all.select([*_KEY, "flags"]), on=_KEY, how="left").with_columns(
        pl.col("flags").fill_null(0)
    )
    big = big.filter((pl.col("flags") == 0) & (pl.col("bid") > 0)).with_columns(
        mid=(pl.col("bid") + pl.col("ask")) / 2.0,
        session=pl.col("ts").dt.date(),
    )
    big = big.join(
        forwards_all.select("ts", "expiry_date", "forward_hat", "df_hat", "tau_years", "parity_ok"),
        on=["ts", "expiry_date"],
        how="inner",
    ).filter(pl.col("parity_ok"))
    big = big.sort(["session", "expiry_date", "cp", "strike"])

    # one giant vectorized IV + delta solve
    mid_np = big["mid"].to_numpy()
    f_np = big["forward_hat"].to_numpy()
    k_np = big["strike"].to_numpy()
    tau_np = big["tau_years"].to_numpy()
    df_np = big["df_hat"].to_numpy()
    w_np = np.where(big["cp"].to_numpy() == "C", 1, -1)
    iv_np = implied_vol(mid_np, f_np, k_np, tau_np, df_np, cp=w_np)
    g = greeks(f_np, k_np, tau_np, np.where(np.isfinite(iv_np), iv_np, 0.2), df_np, cp=w_np)
    delta_abs = np.where(np.isfinite(iv_np), np.abs(g.delta / df_np), np.nan)

    big = big.with_columns(_iv=pl.Series(iv_np), _delta=pl.Series(delta_abs))

    by_session: dict[dt.date, SessionData] = {}
    daily = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    closes = dict(
        daily.group_by("session", maintain_order=True).agg(pl.col("close").last()).iter_rows()
    )

    for (session,), grp in big.group_by(["session"], maintain_order=True):
        sides: dict[tuple[dt.date, str], Side] = {}
        forwards: dict[dt.date, tuple[float, float, float]] = {}
        for (expiry, cp), sgrp in grp.group_by(["expiry_date", "cp"], maintain_order=True):
            sides[(expiry, cp)] = Side(
                strikes=sgrp["strike"].to_numpy(),
                bid=sgrp["bid"].to_numpy(),
                ask=sgrp["ask"].to_numpy(),
                mid=sgrp["mid"].to_numpy(),
                bid_size=sgrp["bid_size"].to_numpy(),
                ask_size=sgrp["ask_size"].to_numpy(),
                iv=sgrp["_iv"].to_numpy(),
                delta_abs=sgrp["_delta"].to_numpy(),
            )
            if expiry not in forwards:
                forwards[expiry] = (
                    float(sgrp["forward_hat"][0]),
                    float(sgrp["df_hat"][0]),
                    float(sgrp["tau_years"][0]),
                )
        by_session[session] = SessionData(
            session=session,
            expiries=sorted({e for e, _ in sides}),
            sides=sides,
            forwards=forwards,
            close=float(closes[session]),
        )

    settle_df = adapter.settlements().filter(pl.col("root") == "SPXW")
    settlements = {r["expiry_date"]: r["value"] for r in settle_df.iter_rows(named=True)}

    cache = WorldCache(
        sessions=session_list,
        by_session=by_session,
        settlements=settlements,
        entry_flags=entry_flags,
    )

    daily_ohlc = daily.group_by("session", maintain_order=True).agg(
        open=pl.col("open").first(),
        high=pl.col("high").max(),
        low=pl.col("low").min(),
        close=pl.col("close").last(),
    )
    for ema_len, h in ema_hyst_combos:
        cfg = RegimeConfig(ema_len=ema_len, hysteresis_atr=h)
        table: dict[dt.date, tuple[str, str]] = {}
        for i, session in enumerate(session_list):
            if not entry_flags[i]:
                continue
            hist = daily_ohlc[:i]
            if hist.height == 0:
                table[session] = ("warmup", "none")
                continue
            frame = regime_frame(hist, cfg)
            completed = frame.filter(frame["state"] != "warmup")
            if completed.height == 0:
                table[session] = ("warmup", "none")
            else:
                row = completed.row(completed.height - 1, named=True)
                table[session] = (row["state"], row["event"])
        cache.regime_allow[(ema_len, h)] = table
    return cache
