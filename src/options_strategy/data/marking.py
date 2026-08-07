"""Position marks (PLAN §6): NBBO mid when the quote is sane and two-sided,
otherwise Black-76 at strike-interpolated IV with marked_from_model=True.
Rows that can be neither mid-marked nor model-marked get a null mark — the
portfolio layer must decide (it never silently invents a price).
"""

from __future__ import annotations

import numpy as np
import polars as pl

from options_strategy.pricing import black76
from options_strategy.pricing.iv import implied_vol

_KEY = ["ts", "root", "expiry_date", "strike", "cp"]


def mark_chain(
    quotes: pl.DataFrame,
    flags: pl.DataFrame | None,
    forwards: pl.DataFrame,
) -> pl.DataFrame:
    """Returns quotes + [mark, marked_from_model].

    forwards: per (ts, root, expiry_date): df_hat, forward_hat, tau_years
    (the QA gate's forwards_extracted table or an equivalent parity fit).
    """
    df = quotes.with_columns(
        mid=(pl.col("bid") + pl.col("ask")) / 2.0,
    )
    if flags is not None and flags.height:
        df = df.join(flags.select([*_KEY, "flags"]), on=_KEY, how="left").with_columns(
            pl.col("flags").fill_null(0)
        )
    else:
        df = df.with_columns(flags=pl.lit(0, dtype=pl.Int32))

    df = df.with_columns(
        _sane=(pl.col("flags") == 0) & (pl.col("bid") > 0),
    )
    df = df.with_columns(
        mark=pl.when(pl.col("_sane")).then(pl.col("mid")).otherwise(None),
        marked_from_model=pl.lit(False),
    )

    bad = df.filter(~pl.col("_sane"))
    if bad.height == 0:
        return df.drop(["_sane"])

    fwd = forwards.select("ts", "root", "expiry_date", "df_hat", "forward_hat", "tau_years")
    out_marks: list[pl.DataFrame] = []
    for (ts, root, expiry), grp in bad.group_by(["ts", "root", "expiry_date"], maintain_order=True):
        fit = fwd.filter(
            (pl.col("ts") == ts) & (pl.col("root") == root) & (pl.col("expiry_date") == expiry)
        )
        if fit.height != 1:
            continue
        f_hat, df_hat, tau = (
            fit["forward_hat"][0],
            fit["df_hat"][0],
            fit["tau_years"][0],
        )
        sane_side = df.filter(
            (pl.col("ts") == ts)
            & (pl.col("root") == root)
            & (pl.col("expiry_date") == expiry)
            & pl.col("_sane")
        )
        for cp_name in grp["cp"].unique().to_list():
            anchors = sane_side.filter(pl.col("cp") == cp_name).sort("strike")
            if anchors.height < 2:
                continue
            ak = anchors["strike"].to_numpy()
            aiv = implied_vol(
                anchors["mid"].to_numpy(), f_hat, ak, tau, df_hat, cp=1 if cp_name == "C" else -1
            )
            good = np.isfinite(aiv)
            if good.sum() < 2:
                continue
            targets = grp.filter(pl.col("cp") == cp_name)
            tk = targets["strike"].to_numpy()
            interp_iv = np.interp(tk, ak[good], aiv[good])
            model = black76.price(f_hat, tk, tau, interp_iv, df_hat, cp=1 if cp_name == "C" else -1)
            out_marks.append(
                targets.select(_KEY).with_columns(
                    _model_mark=pl.Series(model),
                )
            )

    if out_marks:
        model_df = pl.concat(out_marks)
        df = (
            df.join(model_df, on=_KEY, how="left")
            .with_columns(
                mark=pl.when(pl.col("mark").is_null() & pl.col("_model_mark").is_not_null())
                .then(pl.col("_model_mark"))
                .otherwise(pl.col("mark")),
                marked_from_model=pl.col("_model_mark").is_not_null() & ~pl.col("_sane"),
            )
            .drop("_model_mark")
        )

    return df.drop(["_sane"])
