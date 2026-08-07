"""Analytic Black-76 greeks (PLAN §6).

Conventions (documented, tested against finite differences):
- delta: forward delta dV/dF (df * omega * N(omega*d1)).
- gamma: d2V/dF2 (df * phi(d1) / (F * sigma * sqrt(tau))).
- vega:  dV/dsigma per 1.0 of vol (divide by 100 for per-vol-point).
- theta: dV/dt at fixed F and sigma, per YEAR (negative for long options);
         includes the discounting term r*V with r inferred from df and tau.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr

from options_strategy.pricing.black76 import cp_sign

_SQRT_2PI = float(np.sqrt(2.0 * np.pi))


@dataclass(frozen=True)
class Greeks:
    delta: np.ndarray
    gamma: np.ndarray
    vega: np.ndarray
    theta: np.ndarray


def _phi(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / _SQRT_2PI


def greeks(
    forward: np.ndarray | float,
    strike: np.ndarray | float,
    tau: np.ndarray | float,
    sigma: np.ndarray | float,
    df: np.ndarray | float = 1.0,
    cp: np.ndarray | int = 1,
) -> Greeks:
    f = np.asarray(forward, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    t = np.asarray(tau, dtype=np.float64)
    s = np.asarray(sigma, dtype=np.float64)
    d = np.asarray(df, dtype=np.float64)
    w = np.asarray(cp_sign(cp) if not isinstance(cp, int) else cp, dtype=np.float64)
    f, k, t, s, d, w = np.broadcast_arrays(f, k, t, s, d, w)

    live = (t > 0.0) & (s > 0.0) & (f > 0.0) & (k > 0.0)
    sqrt_t = np.sqrt(np.where(live, t, 1.0))
    vol = np.where(live, s, 1.0) * sqrt_t
    d1 = np.log(np.where(live, f, 1.0) / np.where(live, k, 1.0)) / vol + 0.5 * vol
    d2 = d1 - vol
    pdf1 = _phi(d1)

    r = np.where(live & (d > 0), -np.log(np.where(d > 0, d, 1.0)) / np.where(live, t, 1.0), 0.0)
    value = d * w * (f * ndtr(w * d1) - k * ndtr(w * d2))

    delta = np.where(live, d * w * ndtr(w * d1), d * w * (w * (f - k) > 0))
    gamma = np.where(live, d * pdf1 / (f * vol / sqrt_t * sqrt_t), 0.0)
    vega = np.where(live, d * f * pdf1 * sqrt_t, 0.0)
    theta = np.where(live, -d * f * pdf1 * s / (2.0 * sqrt_t) + r * value, 0.0)
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
