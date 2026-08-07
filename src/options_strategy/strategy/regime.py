"""21-EMA weekly regime module (PLAN §8.3).

Definitions (parameterized; ranges are sweep priors):
- Weekly bars aggregate daily candles by ISO week; the week stamp is its last
  session. EMA uses the classic convention: seeded with the SMA of the first
  `ema_len` weekly closes, then recursive with alpha = 2/(len+1). ATR uses
  Wilder smoothing (alpha = 1/len) on weekly true range.
- state: bull if close > ema else bear (evaluated on completed weeks).
- crossover: state flipped vs the prior week.
- retracement: state stays bull, and the week's low dipped into the band
  [ema - h*atr, ema + h*atr] while the close held at/above ema.
- rejection: state stays bear, and the week's high reached up into the band
  while the close stayed at/below ema.
Precedence: crossover > retracement > rejection > none.

`reference_events` is an independent, deliberately naive pure-Python
implementation used only by tests (PLAN §12 P3 AC: production must match it
on scripted synthetic candles).
"""

from __future__ import annotations

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict

EVENT_NONE = "none"
EVENT_CROSSOVER = "crossover"
EVENT_RETRACEMENT = "retracement"
EVENT_REJECTION = "rejection"


class RegimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ema_len: int = 21
    atr_len: int = 14
    hysteresis_atr: float = 0.0  # h in {0, 0.25, 0.5} * weekly ATR


def weekly_bars(daily: pl.DataFrame) -> pl.DataFrame:
    """daily: [session, open, high, low, close] -> ISO-weekly bars."""
    df = daily.sort("session").with_columns(
        iso_year=pl.col("session").dt.iso_year(),
        iso_week=pl.col("session").dt.week(),
    )
    return (
        df.group_by(["iso_year", "iso_week"], maintain_order=True)
        .agg(
            week_end=pl.col("session").last(),
            open=pl.col("open").first(),
            high=pl.col("high").max(),
            low=pl.col("low").min(),
            close=pl.col("close").last(),
            n_sessions=pl.len(),
        )
        .drop(["iso_year", "iso_week"])
    )


def ema(values: np.ndarray, length: int) -> np.ndarray:
    """SMA-seeded recursive EMA; NaN until the seed completes."""
    out = np.full(len(values), np.nan)
    if len(values) < length:
        return out
    alpha = 2.0 / (length + 1.0)
    out[length - 1] = values[:length].mean()
    for i in range(length, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.full(n, np.nan)
    if n < length:
        return out
    out[length - 1] = tr[:length].mean()
    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def regime_frame(daily: pl.DataFrame, cfg: RegimeConfig) -> pl.DataFrame:
    """Weekly frame with ema, atr, state and event columns (completed weeks)."""
    wk = weekly_bars(daily)
    close = wk["close"].to_numpy()
    high = wk["high"].to_numpy()
    low = wk["low"].to_numpy()
    ema_v = ema(close, cfg.ema_len)
    atr_v = wilder_atr(high, low, close, cfg.atr_len)

    n = len(close)
    state = np.array(["warmup"] * n, dtype=object)
    event = np.array([EVENT_NONE] * n, dtype=object)
    for i in range(n):
        if np.isnan(ema_v[i]):
            continue
        state[i] = "bull" if close[i] > ema_v[i] else "bear"
        if i == 0 or state[i - 1] == "warmup":
            continue
        band = cfg.hysteresis_atr * (atr_v[i] if not np.isnan(atr_v[i]) else 0.0)
        lo_band, hi_band = ema_v[i] - band, ema_v[i] + band
        if state[i] != state[i - 1]:
            event[i] = EVENT_CROSSOVER
        elif state[i] == "bull" and low[i] <= hi_band and close[i] >= ema_v[i]:
            event[i] = EVENT_RETRACEMENT
        elif state[i] == "bear" and high[i] >= lo_band and close[i] <= ema_v[i]:
            event[i] = EVENT_REJECTION
    return wk.with_columns(
        ema=pl.Series(ema_v),
        atr=pl.Series(atr_v),
        state=pl.Series(state, dtype=pl.String),
        event=pl.Series(event, dtype=pl.String),
    )


def reference_events(
    weekly_ohlc: list[tuple[float, float, float, float]], ema_len: int, atr_len: int, h: float
) -> list[tuple[str, str]]:
    """Independent naive implementation for tests: [(state, event)] per week.

    Deliberately written from the definitions, sharing no code with the
    production path above.
    """
    closes = [c for _, _, _, c in weekly_ohlc]
    highs = [hh for _, hh, _, _ in weekly_ohlc]
    lows = [ll for _, _, ll, _ in weekly_ohlc]

    emas: list[float | None] = [None] * len(closes)
    if len(closes) >= ema_len:
        prev = sum(closes[:ema_len]) / ema_len
        emas[ema_len - 1] = prev
        k = 2.0 / (ema_len + 1.0)
        for i in range(ema_len, len(closes)):
            prev = closes[i] * k + prev * (1 - k)
            emas[i] = prev

    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[0] - lows[0])
        else:
            trs.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
    atrs: list[float | None] = [None] * len(closes)
    if len(closes) >= atr_len:
        prev_a = sum(trs[:atr_len]) / atr_len
        atrs[atr_len - 1] = prev_a
        for i in range(atr_len, len(closes)):
            prev_a = (prev_a * (atr_len - 1) + trs[i]) / atr_len
            atrs[i] = prev_a

    out: list[tuple[str, str]] = []
    prev_state: str | None = None
    for i in range(len(closes)):
        if emas[i] is None:
            out.append(("warmup", EVENT_NONE))
            prev_state = None
            continue
        st = "bull" if closes[i] > emas[i] else "bear"
        ev = EVENT_NONE
        if prev_state is not None:
            band = h * (atrs[i] or 0.0)
            if st != prev_state:
                ev = EVENT_CROSSOVER
            elif st == "bull" and lows[i] <= emas[i] + band and closes[i] >= emas[i]:
                ev = EVENT_RETRACEMENT
            elif st == "bear" and highs[i] >= emas[i] - band and closes[i] <= emas[i]:
                ev = EVENT_REJECTION
        out.append((st, ev))
        prev_state = st
    return out
