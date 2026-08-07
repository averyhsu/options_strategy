"""Parity-extracted forwards (PLAN §4.2 check 1, §6): the forward curve the
pricing layer runs on. Regressing C - P on K gives slope -DF and intercept
DF*F — no dividend model anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParityFit:
    df: float
    forward: float
    rmse: float
    n_strikes: int

    @property
    def plausible(self) -> bool:
        return 0.3 < self.df <= 1.02 and np.isfinite(self.forward) and self.forward > 0


def fit_parity(strikes: np.ndarray, call_mids: np.ndarray, put_mids: np.ndarray) -> ParityFit:
    """OLS of (C - P) on K. Requires >= 2 distinct strikes."""
    k = np.asarray(strikes, dtype=np.float64)
    y = np.asarray(call_mids, dtype=np.float64) - np.asarray(put_mids, dtype=np.float64)
    a_mat = np.column_stack([np.ones_like(k), k])
    coef, _, _, _ = np.linalg.lstsq(a_mat, y, rcond=None)
    resid = y - a_mat @ coef
    df_hat = float(-coef[1])
    f_hat = float(coef[0] / df_hat) if df_hat > 1e-9 else float("nan")
    return ParityFit(
        df=df_hat,
        forward=f_hat,
        rmse=float(np.sqrt(np.mean(resid**2))),
        n_strikes=len(k),
    )
