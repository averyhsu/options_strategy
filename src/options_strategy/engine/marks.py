"""Marks for HELD positions at a snapshot (PLAN §6 marking rules).

Sane two-sided quote -> NBBO mid. Otherwise -> Black-76 at strike-interpolated
IV from the expiry's sane quotes (marked_from_model). A position whose expiry
has no usable parity fit or anchors cannot be priced — that raises, it is
never silently invented.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from options_strategy.engine.instruments import INDEX, Instrument, OptionKey
from options_strategy.engine.marketview import MarketView
from options_strategy.engine.portfolio import EngineInvariantError, Portfolio
from options_strategy.pricing import black76
from options_strategy.pricing.iv import implied_vol


def mark_positions(portfolio: Portfolio, view: MarketView) -> dict[Instrument, float]:
    marks: dict[Instrument, float] = {}
    if INDEX in portfolio.positions:
        marks[INDEX] = view.spot

    for key in portfolio.option_positions():
        q = view.quote(key)
        if q is not None and q.sane and q.bid > 0:
            marks[key] = (q.bid + q.ask) / 2.0
            continue
        marks[key] = _model_mark(key, view)
    return marks


def _model_mark(key: OptionKey, view: MarketView) -> float:
    fit = view.forward(key.root, key.expiry)
    if fit is None:
        raise EngineInvariantError(
            f"cannot mark {key}: no parity fit for {key.root} {key.expiry} at {view.ts}"
        )
    f_hat, df_hat, tau = fit
    anchors = (
        view.chain(root=key.root, expiry=key.expiry, sane_only=True)
        .filter((pl.col("cp") == key.cp) & (pl.col("bid") > 0))
        .sort("strike")
    )
    if anchors.height < 2:
        raise EngineInvariantError(
            f"cannot mark {key}: <2 sane anchors on {key.root} {key.expiry} {key.cp}"
        )
    ak = anchors["strike"].to_numpy()
    mids = ((anchors["bid"] + anchors["ask"]) / 2.0).to_numpy()
    aiv = implied_vol(mids, f_hat, ak, tau, df_hat, cp=1 if key.cp == "C" else -1)
    good = np.isfinite(aiv)
    if good.sum() < 2:
        raise EngineInvariantError(f"cannot mark {key}: no solvable anchor IVs")
    iv_k = float(np.interp(key.strike, ak[good], aiv[good]))
    return float(black76.price(f_hat, key.strike, tau, iv_k, df_hat, cp=1 if key.cp == "C" else -1))
