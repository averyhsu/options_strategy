import numpy as np
import polars as pl

from options_strategy.data.adapters import SyntheticWorldAdapter
from options_strategy.data.synthetic.surface import (
    expected_total_variance,
)
from options_strategy.data.synthetic.surface import (
    implied_vol as surface_iv,
)
from options_strategy.pricing.greeks import greeks
from options_strategy.pricing.iv import implied_vol


def test_extracted_forwards_match_generator_truth(clean_world, clean_world_qa) -> None:
    """PLAN §12 P1 AC: parity forwards ~= generator truth."""
    _, paths, _ = clean_world
    fw = pl.read_parquet(clean_world_qa.forwards_path)
    truth = pl.read_parquet(paths.truth_forwards)
    joined = fw.join(truth, on=["ts", "root", "expiry_date"], how="inner")
    assert joined.height > 500
    rel = ((joined["forward_hat"] - joined["forward"]).abs() / joined["forward"]).to_numpy()
    assert rel.max() <= 2e-4
    gated = joined.filter(pl.col("tau_years") >= 7 / 365)
    assert (gated["df_hat"] - gated["df"]).abs().max() <= 7.5e-4


def test_iv_of_sane_mids_recovers_surface_truth(clean_world, clean_world_qa) -> None:
    """Chain mids -> implied_vol at truth forwards must recover the SSVI truth
    surface within quote-noise tolerance (ties world pricing, iv solver, and
    surface together)."""
    cfg, paths, _ = clean_world
    adapter = SyntheticWorldAdapter(paths.root)
    session = adapter.sessions()["session"][3]
    quotes = adapter.option_quotes(session)
    truth = pl.read_parquet(paths.truth_forwards).filter(pl.col("ts").dt.date() == session)

    q = (
        quotes.filter(pl.col("bid") > 0)
        .with_columns(mid=(pl.col("bid") + pl.col("ask")) / 2.0)
        .join(truth, on=["ts", "root", "expiry_date"], how="inner")
    )
    assert q.height > 100

    w = np.where(q["cp"].to_numpy() == "C", 1, -1)
    f = q["forward"].to_numpy()
    k = q["strike"].to_numpy()
    ts_naive = q["ts"].dt.replace_time_zone(None).to_numpy()
    expiry_midnight = q["expiry_date"].cast(pl.Datetime("us")).to_numpy()
    settle_sec = np.where(q["am_pm_settle"].to_numpy() == "PM", 16 * 3600.0, 9.5 * 3600.0)
    tau = (
        (expiry_midnight - ts_naive).astype("timedelta64[s]").astype(np.float64) + settle_sec
    ) / (365.0 * 86400.0)
    iv_hat = implied_vol(q["mid"].to_numpy(), f, k, tau, q["df"].to_numpy(), cp=w)

    theta_t = expected_total_variance(q["v_t"].to_numpy(), tau, cfg.heston)
    iv_true = surface_iv(np.log(k / f), tau, theta_t, cfg.surface)

    g = greeks(f, k, tau, iv_true, q["df"].to_numpy(), cp=w)
    liquid = np.isfinite(iv_hat) & (g.vega > 100.0)
    assert liquid.sum() > 50
    err = np.abs(iv_hat[liquid] - iv_true[liquid])
    # Mid sits within half a tick of theo; iv noise ~ tick/(2*vega):
    assert np.median(err) < 1e-3
    assert err.max() < 5e-3
