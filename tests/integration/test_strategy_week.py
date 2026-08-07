"""P3 acceptance on the tiny clean world: hand-specified week golden (AC a),
Track A == Track B (AC c), defense smoke, and the no-lookahead property
(invariant §11.2a)."""

import datetime as dt

import polars as pl
import pytest

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import run_backtest
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.orders import FillModel
from options_strategy.engine.track_a import run_track_a
from options_strategy.strategy.defense import DefenseConfig
from options_strategy.strategy.diagonal import ExplicitLegs, StructureConfig
from options_strategy.strategy.entry import EntryConfig
from options_strategy.strategy.weekly import DoubleDiagonalWeekly, SizingConfig, WeeklyConfig

OPT_CFG = EngineConfig(fill_model=FillModel.OPTIMISTIC)


@pytest.fixture(scope="module")
def adapter(clean_world, clean_world_qa) -> SyntheticWorldAdapter:
    _, paths, _ = clean_world
    assert clean_world_qa.clean
    return SyntheticWorldAdapter(paths.root)


def _eod_chain(adapter: SyntheticWorldAdapter, session: dt.date) -> pl.DataFrame:
    q = adapter.option_quotes(session)
    return q.filter(pl.col("ts") == q["ts"].max()).with_columns(
        mid=(pl.col("bid") + pl.col("ask")) / 2.0
    )


def _pick(chain: pl.DataFrame, expiry: dt.date, cp: str, cond) -> float:
    side = chain.filter(
        (pl.col("expiry_date") == expiry) & (pl.col("cp") == cp) & (pl.col("bid") > 0) & cond
    ).sort("strike")
    assert side.height > 0
    return float(side["strike"][-1 if cp == "P" else 0])


def _mid_of(chain: pl.DataFrame, expiry: dt.date, strike: float, cp: str) -> float:
    row = chain.filter(
        (pl.col("expiry_date") == expiry) & (pl.col("strike") == strike) & (pl.col("cp") == cp)
    )
    assert row.height == 1
    return float(row["mid"][0])


def _explicit_cfg(adapter: SyntheticWorldAdapter, near: float = 0.99) -> tuple[WeeklyConfig, dict]:
    """Hand-specify a week on the world's first Friday from its actual chain."""
    entry_session = dt.date(2026, 3, 6)
    chain = _eod_chain(adapter, entry_session)
    spot_proxy = float(chain.filter(pl.col("cp") == "C").sort("strike")["strike"].median())
    front = dt.date(2026, 3, 13)
    back = dt.date(2026, 3, 16)
    sp = _pick(chain, front, "P", pl.col("strike") <= spot_proxy * near)
    sc = _pick(chain, front, "C", pl.col("strike") >= spot_proxy * (2 - near))
    lp = _pick(chain, back, "P", pl.col("strike") <= sp - 20.0)
    lc = _pick(chain, back, "C", pl.col("strike") >= sc + 20.0)
    legs = ExplicitLegs(
        front_expiry=front,
        back_put_expiry=back,
        back_call_expiry=back,
        short_put=sp,
        short_call=sc,
        long_put=lp,
        long_call=lc,
    )
    cfg = WeeklyConfig(
        structure=StructureConfig(explicit=legs, min_credit_frac=0.0, require_credit=False),
        entry=EntryConfig(execution="eod_mid", credit_threshold_frac=0.0),
        sizing=SizingConfig(risk_fraction=0.15, max_contracts=1),
        defense=DefenseConfig(trigger="none"),
        regime_action="trade_all",
    )
    info = {"entry_session": entry_session, "front": front, "back": back, "legs": legs}
    return cfg, info


def test_hand_specified_week_reproduces_hand_calculated_pnl(adapter) -> None:
    """PLAN §12 P3 AC: a fully hand-specified example week reproduces
    hand-calculated P&L. Expected values are recomputed here from the raw
    parquet files with plain arithmetic — no engine code."""
    cfg, info = _explicit_cfg(adapter)
    result = run_backtest(adapter, DoubleDiagonalWeekly(cfg), OPT_CFG, initial_cash=100_000.0)
    p = result.portfolio
    entry_fills = [f for f in p.fills if f.ts.date() == info["entry_session"]]
    assert len(entry_fills) == 1 and entry_fills[0].qty == 1
    fill = entry_fills[0]

    # ---- independent recomputation from raw files ----
    chain = _eod_chain(adapter, info["entry_session"])
    legs = info["legs"]
    mids = {
        "sp": _mid_of(chain, legs.front_expiry, legs.short_put, "P"),
        "sc": _mid_of(chain, legs.front_expiry, legs.short_call, "C"),
        "lp": _mid_of(chain, legs.back_put_expiry, legs.long_put, "P"),
        "lc": _mid_of(chain, legs.back_call_expiry, legs.long_call, "C"),
    }
    credit = mids["sp"] + mids["sc"] - mids["lp"] - mids["lc"]
    assert fill.price_debit == pytest.approx(-credit, abs=1e-12)
    assert fill.fees == pytest.approx(4 * 1.60, abs=1e-12)

    # entry-day NAV: value unchanged at the fill mark, so NAV = initial - fees
    entry_nav = result.daily.filter(pl.col("session") == info["entry_session"])["nav"][0]
    assert entry_nav == pytest.approx(100_000.0 - 6.40, abs=1e-9)

    settlements = pl.read_parquet(adapter.paths.settlements)

    def settle_value(expiry: dt.date) -> float:
        return float(
            settlements.filter((pl.col("expiry_date") == expiry) & (pl.col("root") == "SPXW"))[
                "value"
            ][0]
        )

    front_print = settle_value(legs.front_expiry)
    back_print = settle_value(legs.back_put_expiry)  # both backs expire 03-16
    short_put_intrinsic = max(legs.short_put - front_print, 0.0)
    short_call_intrinsic = max(front_print - legs.short_call, 0.0)
    long_put_intrinsic = max(legs.long_put - back_print, 0.0)
    long_call_intrinsic = max(back_print - legs.long_call, 0.0)

    # Both expiries settle inside the window, so the book ends flat:
    # NAV = initial - fees + credit*100 - short intrinsics*100 + long intrinsics*100.
    expected_final_nav = (
        100_000.0
        - 6.40
        + credit * 100.0
        - (short_put_intrinsic + short_call_intrinsic) * 100.0
        + (long_put_intrinsic + long_call_intrinsic) * 100.0
    )
    final_nav = result.daily["nav"][-1]
    assert final_nav == pytest.approx(expected_final_nav, abs=1e-6)
    assert len(p.settlements) == 4  # all four legs settled (ITM or worth 0)
    assert not p.positions


def _delta_cfg(execution: str = "eod_mid") -> WeeklyConfig:
    return WeeklyConfig(
        structure=StructureConfig(
            short_put_delta=0.25,
            short_call_delta=0.20,
            long_put_expiry_offset_days=3,
            long_call_expiry_offset_days=3,
            long_strike_offset=25.0,
            min_credit_frac=0.0,
            require_credit=False,
        ),
        entry=EntryConfig(execution=execution, credit_threshold_frac=0.05),
        sizing=SizingConfig(risk_fraction=0.15),
        defense=DefenseConfig(trigger="none"),
        regime_action="trade_all",
    )


def test_track_a_equals_track_b_on_eod_expressible_config(adapter) -> None:
    """PLAN §3 consistency requirement / §12 P3 AC: |NAV_A - NAV_B| <= 1e-6 rel."""
    cfg = _delta_cfg()
    b = run_backtest(adapter, DoubleDiagonalWeekly(cfg), OPT_CFG, initial_cash=100_000.0)
    a = run_track_a(adapter, cfg, OPT_CFG, initial_cash=100_000.0)
    assert len(b.portfolio.fills) > 0, "Track B never entered — test is vacuous"
    assert len(a.portfolio.fills) == len(b.portfolio.fills)
    nav_a = a.daily["nav"].to_numpy()
    nav_b = b.daily["nav"].to_numpy()
    assert len(nav_a) == len(nav_b)
    rel = abs(nav_a[-1] - nav_b[-1]) / abs(nav_b[-1])
    assert rel <= 1e-6
    assert max(abs(nav_a - nav_b)) <= 1e-6 * 100_000.0


def test_defense_touch_immediate_closes_tested_side(adapter) -> None:
    cfg, _info = _explicit_cfg(adapter, near=0.9995)  # shorts hug the spot: touch is certain
    cfg = cfg.model_copy(
        update={
            "defense": DefenseConfig(
                trigger="touch", timing="immediate", action="close_tested_side"
            )
        }
    )
    strat = DoubleDiagonalWeekly(cfg)
    result = run_backtest(adapter, strat, OPT_CFG, initial_cash=100_000.0)
    assert strat.defense_log, "expected the defense to trigger with ATM shorts"
    entry = strat.defense_log[0]
    assert entry["action"] == "close_tested_side"
    closing = [f for f in result.portfolio.fills if any(r > 0 for _, r in f.legs)]
    assert closing, "defense must have produced a closing fill"


class _MutatedAdapter(SyntheticWorldAdapter):
    """Quotes strictly after the cutoff are perturbed; before it, untouched."""

    def __init__(self, root, cutoff: dt.date):
        super().__init__(root)
        self.cutoff = cutoff

    def option_quotes(self, session: dt.date) -> pl.DataFrame:
        q = super().option_quotes(session)
        if session <= self.cutoff:
            return q
        return q.with_columns(bid=pl.col("bid") * 1.5 + 0.05, ask=pl.col("ask") * 1.5 + 0.35)


def test_no_lookahead_decisions_before_t_are_bit_identical(clean_world, clean_world_qa) -> None:
    """Invariant §11.2a: mutate all data strictly after t => decisions at t
    unchanged."""
    _, paths, _ = clean_world
    cutoff = dt.date(2026, 3, 11)
    cfg = _delta_cfg()
    base = run_backtest(
        SyntheticWorldAdapter(paths.root), DoubleDiagonalWeekly(cfg), OPT_CFG, 100_000.0
    )
    mutated = run_backtest(
        _MutatedAdapter(paths.root, cutoff), DoubleDiagonalWeekly(cfg), OPT_CFG, 100_000.0
    )

    def fills_upto(result):
        return [
            (f.ts, f.legs, f.qty, f.price_debit, f.fees)
            for f in result.portfolio.fills
            if f.ts.date() <= cutoff
        ]

    assert fills_upto(base) == fills_upto(mutated)
    assert len(fills_upto(base)) > 0, "no decisions before the cutoff — test is vacuous"
    a = base.daily.filter(pl.col("session") <= cutoff)
    b = mutated.daily.filter(pl.col("session") <= cutoff)
    assert a.equals(b)
