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

    by_session: dict[dt.date, SessionData] = {}
    daily = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    closes = dict(
        daily.group_by("session", maintain_order=True).agg(pl.col("close").last()).iter_rows()
    )

    # Streamed per-session build: one small frame in memory at a time (this
    # box has 8GB RAM; a whole-world concat of an 18M-row chain got the
    # process OOM-killed).
    for session in session_list:
        q = adapter.option_quotes(session).filter(pl.col("root") == "SPXW")
        eod_ts = q["ts"].max()
        frame = q.filter(pl.col("ts") == eod_ts)
        frame = frame.join(flags_all.select([*_KEY, "flags"]), on=_KEY, how="left").with_columns(
            pl.col("flags").fill_null(0)
        )
        frame = frame.filter((pl.col("flags") == 0) & (pl.col("bid") > 0)).with_columns(
            mid=(pl.col("bid") + pl.col("ask")) / 2.0
        )
        # LEFT join: quotes of expiries WITHOUT a usable parity fit stay
        # tradeable (mids, sizes) — fits only gate IV/delta/model marks.
        frame = frame.join(
            forwards_all.filter(pl.col("ts") == eod_ts).select(
                "expiry_date", "forward_hat", "df_hat", "tau_years", "parity_ok"
            ),
            on=["expiry_date"],
            how="left",
        ).with_columns(pl.col("parity_ok").fill_null(False))
        frame = frame.sort(["expiry_date", "cp", "strike"])

        ok = frame["parity_ok"].to_numpy()
        mid_np = frame["mid"].to_numpy()
        f_np = frame["forward_hat"].fill_null(0.0).to_numpy()
        k_np = frame["strike"].to_numpy()
        tau_np = frame["tau_years"].fill_null(1.0).to_numpy()
        df_np = frame["df_hat"].fill_null(1.0).to_numpy()
        w_np = np.where(frame["cp"].to_numpy() == "C", 1, -1)
        iv_np = np.full(len(mid_np), np.nan)
        if ok.any():
            iv_np[ok] = implied_vol(
                mid_np[ok], f_np[ok], k_np[ok], tau_np[ok], df_np[ok], cp=w_np[ok]
            )
        delta_abs = np.full(len(mid_np), np.nan)
        solvable = np.isfinite(iv_np)
        if solvable.any():
            g = greeks(
                f_np[solvable],
                k_np[solvable],
                tau_np[solvable],
                iv_np[solvable],
                df_np[solvable],
                cp=w_np[solvable],
            )
            delta_abs[solvable] = np.abs(g.delta / df_np[solvable])
        frame = frame.with_columns(_iv=pl.Series(iv_np), _delta=pl.Series(delta_abs))

        sides: dict[tuple[dt.date, str], Side] = {}
        forwards: dict[dt.date, tuple[float, float, float]] = {}
        for (expiry, cp), sgrp in frame.group_by(["expiry_date", "cp"], maintain_order=True):
            sides[(expiry, cp)] = Side(
                strikes=sgrp["strike"].to_numpy(),
                mid=sgrp["mid"].to_numpy(),
                bid_size=sgrp["bid_size"].to_numpy(),
                ask_size=sgrp["ask_size"].to_numpy(),
                iv=sgrp["_iv"].to_numpy(),
                delta_abs=sgrp["_delta"].to_numpy(),
            )
            if expiry not in forwards and sgrp["parity_ok"][0]:
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
