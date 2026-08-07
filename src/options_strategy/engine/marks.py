"""Marks for HELD positions at a snapshot (PLAN §6 marking rules).

Fallback chain, in order: (1) expiring-today PM legs pin to intrinsic of the
settlement print; (2) sane two-sided NBBO mid; (3) Black-76 at
strike-interpolated IV from the expiry's sane quotes (marked_from_model);
(4) when an expiry has NO usable parity fit or anchors (thin stressed chains
near expiry), the leg pins to intrinsic at spot — conservative for long wings
(0 when OTM), off by at most the quote's pennies. Nothing is ever interpolated
from thin air beyond that floor.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from options_strategy.engine.instruments import INDEX, Instrument, OptionKey
from options_strategy.engine.marketview import MarketView
from options_strategy.engine.portfolio import Portfolio
from options_strategy.pricing import black76
from options_strategy.pricing.iv import implied_vol


def mark_positions(portfolio: Portfolio, view: MarketView) -> dict[Instrument, float]:
    marks: dict[Instrument, float] = {}
    if INDEX in portfolio.positions:
        marks[INDEX] = view.spot

    for key in portfolio.option_positions():
        if key.expiry == view.session_date and key.settlement == "PM":
            # Expiring today: pins to intrinsic of the settlement print (the
            # session close). Exact at the EOD mark; a lower bound intraday.
            w = 1.0 if key.cp == "C" else -1.0
            marks[key] = max(w * (view.spot - key.strike), 0.0)
            continue
        q = view.quote(key)
        if q is not None and q.sane and q.bid > 0:
            marks[key] = (q.bid + q.ask) / 2.0
            continue
        model = _model_mark(key, view)
        if model is not None:
            marks[key] = model
        else:  # unmarkable wing: intrinsic-at-spot floor (see module docstring)
            w = 1.0 if key.cp == "C" else -1.0
            marks[key] = max(w * (view.spot - key.strike), 0.0)
    return marks


def _model_mark(key: OptionKey, view: MarketView) -> float | None:
    fit = view.forward(key.root, key.expiry)
    if fit is None:
        return None
    f_hat, df_hat, tau = fit
    anchors = (
        view.chain(root=key.root, expiry=key.expiry, sane_only=True)
        .filter((pl.col("cp") == key.cp) & (pl.col("bid") > 0))
        .sort("strike")
    )
    if anchors.height < 2:
        return None
    ak = anchors["strike"].to_numpy()
    mids = ((anchors["bid"] + anchors["ask"]) / 2.0).to_numpy()
    aiv = implied_vol(mids, f_hat, ak, tau, df_hat, cp=1 if key.cp == "C" else -1)
    good = np.isfinite(aiv)
    if good.sum() < 2:
        return None
    iv_k = float(np.interp(key.strike, ak[good], aiv[good]))
    return float(black76.price(f_hat, key.strike, tau, iv_k, df_hat, cp=1 if key.cp == "C" else -1))
