"""Credit-check validation on synthetic snapshots (PLAN §1.6 2026-08-16
action 1): debit metrics must compute correctly on a real chain surface
before the vendor mini-slice lands."""

import datetime as dt

import polars as pl
import pytest

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.data.qa import run_qa
from options_strategy.data.synthetic.config import ChainParams, SnapshotSpec, SyntheticWorldConfig
from options_strategy.data.synthetic.world import generate_world
from options_strategy.eval.credit_check import run_credit_check


@pytest.fixture(scope="module")
def snapshot_world(tmp_path_factory):
    root = tmp_path_factory.mktemp("ccworld")
    cfg = SyntheticWorldConfig(
        name="credit-check-synthetic",
        seed=23,
        start=dt.date(2026, 2, 2),
        end=dt.date(2026, 3, 20),
        # 2026 era lists DAILY expiries: 25 slots ~ 5 weeks of tenors, enough
        # for a 7d front plus a 21d-beyond back leg
        chain=ChainParams(n_weeklies=25, n_monthlies=1, near_band_pct=0.03, span_pct=0.06),
        snapshots=SnapshotSpec(eod=True),
    )
    paths, _ = generate_world(cfg, root)
    assert run_qa(paths.root).clean
    return SyntheticWorldAdapter(paths.root)


def _eod_inputs(adapter, session: dt.date):
    q = adapter.option_quotes(session).filter(pl.col("root") == "SPXW")
    eod_ts = q["ts"].max()
    chain = q.filter(pl.col("ts") == eod_ts)
    fwd = adapter.forwards_extracted().filter(
        (pl.col("ts") == eod_ts) & (pl.col("root") == "SPXW") & pl.col("parity_ok")
    )
    fits = {
        r["expiry_date"]: (r["forward_hat"], r["df_hat"], r["tau_years"])
        for r in fwd.iter_rows(named=True)
    }
    daily = adapter.underlying_bars().with_columns(session=pl.col("ts").dt.date())
    spot = float(daily.filter(pl.col("session") == session)["close"][-1])
    return chain, spot, fits


def test_dual_metrics_on_synthetic_snapshot(snapshot_world) -> None:
    session = dt.date(2026, 2, 20)  # a Friday with 7d front + 21d back available
    chain, spot, fits = _eod_inputs(snapshot_world, session)
    df = run_credit_check(
        chain,
        spot,
        fits,
        session,
        band_edges={"q90": (-0.0211, 0.0208), "q95": (-0.0279, 0.0270)},
        wing_offsets=(0.0, 25.0, 50.0),
    )
    assert df.height > 0
    assert {"q90", "q95", "atm_ref"} <= set(df["label"].unique().to_list())
    # both readings computed and finite everywhere; debits never dropped
    assert df["net_premium_pct_risk"].is_finite().all()
    assert df["max_gain_pct_risk"].is_finite().all()
    # the Pass-1 structural finding, now visible at structure level: on the
    # synthetic surface near-calendar (offset-0) band structures are DEBITS
    cal = df.filter((pl.col("wing_offset") == 0.0) & (pl.col("label") != "atm_ref"))
    assert cal.height > 0
    assert cal["is_debit"].all()
    # reading (b) exists exactly where reading (a) fails: debit calendars
    # still show a computable, bounded max-gain-in-band
    assert (cal["max_gain_pct_risk"] > -1.0).all()
    # geometry sanity: shorts bracket spot, wings at the requested offsets
    for r in df.iter_rows(named=True):
        assert r["short_put"] <= spot <= r["short_call"] or r["label"] == "atm_ref"
        assert abs(r["short_put"] - r["long_put"]) <= r["wing_offset"] + 25.0
        assert r["front_expiry"] < r["back_expiry"]


def test_atm_reference_prices_richer_than_band_edges(snapshot_world) -> None:
    """His 'big credit only ATM/ITM' line: the ATM reference must collect
    strictly more front premium than the q-level structures (same wings)."""
    session = dt.date(2026, 2, 20)
    chain, spot, fits = _eod_inputs(snapshot_world, session)
    df = run_credit_check(
        chain, spot, fits, session, band_edges={"q95": (-0.0279, 0.0270)}, wing_offsets=(25.0,)
    )
    atm = df.filter(pl.col("label") == "atm_ref")
    q95 = df.filter(pl.col("label") == "q95")
    assert atm.height == 1 and q95.height == 1
    # the revenue side — front strangle premium COLLECTED — must be strictly
    # richer at ATM (the net package can still be a bigger debit there, since
    # near-ATM back wings cost more too: both facts are reported, not judged)
    assert atm["front_premium"][0] > q95["front_premium"][0]
