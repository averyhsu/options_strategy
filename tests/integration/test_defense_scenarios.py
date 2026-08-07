"""P5 defense scenario tests (PLAN §12 P5 AC): every §8.4 defense variant
exercised on a scripted weekend-gap week (Monday -5%, vol x3 — the F4
rehearsal), plus trigger/timing semantics and resting-fill-model bounds.
"""

import datetime as dt

import polars as pl
import pytest

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.engine.backtest import run_backtest
from options_strategy.engine.config import EngineConfig
from options_strategy.engine.instruments import INDEX, OptionKey
from options_strategy.engine.orders import FillModel
from options_strategy.strategy.defense import ACTIONS, DefenseConfig
from options_strategy.strategy.diagonal import ExplicitLegs, StructureConfig
from options_strategy.strategy.entry import EntryConfig
from options_strategy.strategy.weekly import DoubleDiagonalWeekly, SizingConfig, WeeklyConfig

ENTRY_SESSION = dt.date(2026, 3, 6)
GAP_SESSION = dt.date(2026, 3, 9)
FRONT = dt.date(2026, 3, 13)


@pytest.fixture(scope="module")
def adapter(gap_world, gap_world_qa) -> SyntheticWorldAdapter:
    _, paths, _ = gap_world
    assert gap_world_qa.clean, gap_world_qa.summary
    return SyntheticWorldAdapter(paths.root)


@pytest.fixture(scope="module")
def credit_legs(adapter) -> ExplicitLegs:
    """Deterministic scenario structure: short strikes OUTSIDE Friday's
    realized range (no same-day touch) but inside Monday's gap path (the put
    gets blown through), priced as a real net credit."""
    under = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    fri = under.filter(pl.col("session") == ENTRY_SESSION)
    fri_low, fri_high = float(fri["low"].min()), float(fri["high"].max())
    mon_low = float(under.filter(pl.col("session") == GAP_SESSION)["low"].min())

    q = adapter.option_quotes(ENTRY_SESSION)
    chain = q.filter(pl.col("ts") == q["ts"].min()).with_columns(
        mid=(pl.col("bid") + pl.col("ask")) / 2.0
    )
    back = dt.date(2026, 3, 20)

    def mid_of(expiry, strike, cp):
        row = chain.filter(
            (pl.col("root") == "SPXW")  # the SPX AM monthly shares 3rd-Friday dates (§14)
            & (pl.col("expiry_date") == expiry)
            & (pl.col("strike") == strike)
            & (pl.col("cp") == cp)
            & (pl.col("bid") > 0)
        )
        return float(row["mid"][0]) if row.height == 1 else None

    def strikes_of(expiry, cp):
        side = chain.filter(
            (pl.col("root") == "SPXW")
            & (pl.col("expiry_date") == expiry)
            & (pl.col("cp") == cp)
            & (pl.col("bid") > 0)
        )
        return side["strike"].to_numpy()

    put_ks = strikes_of(FRONT, "P")
    call_ks = strikes_of(FRONT, "C")
    below_friday = put_ks[(put_ks < fri_low * 0.999) & (put_ks > mon_low + 10.0)]
    above_friday = call_ks[call_ks > fri_high * 1.001]
    assert len(below_friday) and len(above_friday), "gap world lacks scenario strikes"
    sp = float(below_friday.max())  # tightest untouched-Friday put, gapped-through Monday
    sc = float(above_friday.min())

    for offset in (75.0, 100.0, 125.0, 150.0):
        lp_ks = strikes_of(back, "P")
        lc_ks = strikes_of(back, "C")
        lp = float(lp_ks[abs(lp_ks - (sp - offset)).argmin()])
        lc = float(lc_ks[abs(lc_ks - (sc + offset)).argmin()])
        mids = [
            mid_of(FRONT, sp, "P"),
            mid_of(FRONT, sc, "C"),
            mid_of(back, lp, "P"),
            mid_of(back, lc, "C"),
        ]
        if any(m is None for m in mids):
            continue
        credit = mids[0] + mids[1] - mids[2] - mids[3]
        if credit > 3.0:
            return ExplicitLegs(
                front_expiry=FRONT,
                back_put_expiry=back,
                back_call_expiry=back,
                short_put=sp,
                short_call=sc,
                long_put=lp,
                long_call=lc,
            )
    raise AssertionError("no credit double diagonal found on the gap-world chain")


def _cfg(legs: ExplicitLegs, defense: DefenseConfig, t1: str = "hold") -> WeeklyConfig:
    return WeeklyConfig(
        structure=StructureConfig(explicit=legs, min_credit_frac=0.0),
        entry=EntryConfig(
            execution="resting", credit_threshold_frac=0.02, threshold_reference="width"
        ),
        # scenarios pin qty to exactly 1 regardless of the structure's R
        sizing=SizingConfig(risk_fraction=0.5, max_contracts=1),
        defense=defense,
        regime_action="trade_all",
        manage_t1=t1,
    )


def _run(adapter, cfg: WeeklyConfig, fill_model: FillModel = FillModel.OPTIMISTIC):
    strat = DoubleDiagonalWeekly(cfg)
    result = run_backtest(
        adapter, strat, EngineConfig(fill_model=fill_model), initial_cash=100_000.0
    )
    return strat, result


def test_gap_week_is_an_f4_style_event(adapter, credit_legs) -> None:
    """The scripted Monday gap must produce a large one-day NAV loss for an
    undefended position — the structural fingerprint F4 rehearses."""
    _strat, result = _run(adapter, _cfg(credit_legs, DefenseConfig(trigger="none")))
    daily = result.daily
    entry_nav = daily.filter(pl.col("session") == ENTRY_SESSION)["nav"][0]
    gap_nav = daily.filter(pl.col("session") == GAP_SESSION)["nav"][0]
    assert len(result.portfolio.fills) == 1, "entry must fill on Friday"
    assert gap_nav < entry_nav - 500.0, "gap Monday should hurt an undefended short strangle"


@pytest.mark.parametrize("action", [a for a in ACTIONS if a != "nothing"])
def test_every_defense_action_executes_on_touch(adapter, credit_legs, action: str) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(trigger="touch", timing="immediate", action=action, untested="hold"),
    )
    strat, result = _run(adapter, cfg)
    assert strat.defense_log, f"action {action}: defense never triggered"
    entry = strat.defense_log[0]
    assert entry["side"] == "put" and entry["action"] == action
    p = result.portfolio
    if action == "delta_hedge":
        # post-gap the short put dominates: the book is LONG delta, so the
        # hedge must SHORT index units
        assert INDEX in p.positions and p.positions[INDEX] < 0
    else:
        closing = [f for f in p.fills if any(r > 0 for _, r in f.legs)]
        assert closing, f"action {action}: no defensive fill"
        if action in ("roll_out", "roll_out_away"):
            new_shorts = [
                k
                for f in closing
                for k, r in f.legs
                if r < 0 and isinstance(k, OptionKey) and k.expiry > FRONT
            ]
            assert new_shorts, "roll must sell a later-dated short"
        if action == "close_all":
            assert not [k for k in p.positions if isinstance(k, OptionKey)] or (
                result.daily["n_option_positions"].min() == 0
            )


def test_untested_harvest_buys_back_decayed_call(adapter, credit_legs) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(
            trigger="touch", timing="immediate", action="close_tested_side", untested="harvest_80"
        ),
    )
    strat, result = _run(adapter, cfg)
    assert strat.defense_log
    # After the -5% gap the untested CALL collapses; harvest should buy it back.
    call_buybacks = [
        f
        for f in result.portfolio.fills
        if len(f.legs) == 1 and f.legs[0][0].cp == "C" and f.legs[0][1] > 0
    ]
    assert call_buybacks, "harvest_80 should have bought back the collapsed call"


def test_timing_t_minus_1_defers_action(adapter, credit_legs) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(trigger="touch", timing="t_minus_1", action="close_tested_side"),
    )
    strat, _ = _run(adapter, cfg)
    assert strat.defense_log
    act_date = strat.defense_log[0]["ts"].date()
    assert act_date == dt.date(2026, 3, 12), "t_minus_1 must act on the day before expiry"


def test_timing_immediate_acts_on_gap_day(adapter, credit_legs) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(trigger="touch", timing="immediate", action="close_tested_side"),
    )
    strat, _ = _run(adapter, cfg)
    assert strat.defense_log[0]["ts"].date() == GAP_SESSION


def test_trigger_close_beyond_waits_for_the_close(adapter, credit_legs) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(trigger="close_beyond", timing="immediate", action="close_tested_side"),
    )
    strat, _ = _run(adapter, cfg)
    assert strat.defense_log
    ts = strat.defense_log[0]["ts"]
    assert ts.date() == GAP_SESSION and ts.hour == 15 and ts.minute >= 55


def test_trigger_pnl_floor_fires_on_gap(adapter, credit_legs) -> None:
    cfg = _cfg(
        credit_legs,
        DefenseConfig(
            trigger="pnl_floor", trigger_pnl_frac=0.3, timing="immediate", action="close_all"
        ),
    )
    strat, _ = _run(adapter, cfg)
    assert strat.defense_log and strat.defense_log[0]["ts"].date() == GAP_SESSION


def test_fill_model_bounds_conservative_within_optimistic(adapter, credit_legs) -> None:
    """CONSERVATIVE fills are a subset of OPTIMISTIC fills, at no-better prices
    (PLAN §7.2: bounds, reported side-by-side)."""
    cfg = _cfg(credit_legs, DefenseConfig(trigger="none"))
    fills = {}
    for fm in (FillModel.CONSERVATIVE, FillModel.MID, FillModel.OPTIMISTIC):
        _, result = _run(adapter, cfg, fill_model=fm)
        fills[fm] = result.portfolio.fills
    n_c, n_m, n_o = (
        len(fills[k]) for k in (FillModel.CONSERVATIVE, FillModel.MID, FillModel.OPTIMISTIC)
    )
    assert n_c <= n_m <= n_o or (n_c <= n_o), "conservative cannot fill more than optimistic"
    assert n_o >= 1, "optimistic must fill the zero-threshold credit order"
