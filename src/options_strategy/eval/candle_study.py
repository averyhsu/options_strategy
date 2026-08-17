"""Candle study on REAL free daily SPX data (PLAN §8.3, expanded 2026-08-10).

Per the author's 2026-08-10 disclosure, his ENTIRE backtest was this study:
"SPX% return weekly above 21 EMA to estimate historical EV". This module
replicates that research process end-to-end on real candles:

(a) conditional weekly-return distributions above/below the 21-week EMA;
(b) the implied coverage bands and their strike distances (feeds §8.1);
(c) inverse solve on his claims (Kelly ~60%, win ~+30% of R, EV ~+$450/ct);
(d) verify/refute "3 consecutive bad weeks happen below the EMA";
(e) intraweek band-edge touch calendar from daily highs/lows.

**Candles-only.** This is a data-replication study of the OP's methodology —
an explicit user-approved exception to Pass 1's synthetic-only rule (PLAN
§12.0). It simulates NO options positions and makes NO claims about the
options strategy. Actual credit verification waits for Pass 2 options data.

Timing convention (no lookahead): the regime state at week t (close_t vs
EMA_t, both known at Friday's close) conditions week t+1's return and
intraweek extremes — exactly the quantity his stated backtest estimated.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from options_strategy.strategy.regime import RegimeConfig, regime_frame

FREE_ROOT = Path("data/raw/free")
STUDY_START = "1999-01-01"  # EMA warm-up runs from 1995
Q_GRID = [0.80, 0.82, 0.84, 0.85, 0.86, 0.88, 0.90, 0.92, 0.94, 0.95]
PCTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]

# the author's claims (PLAN §1.4/§1.6)
CLAIM_KELLY = 0.60
CLAIM_WIN_PCT_R = 0.30
CLAIM_EV_PER_CONTRACT = 450.0
CLAIM_WR_LO, CLAIM_WR_HI = 0.85, 0.92


def weekly_conditional_frame(daily: pl.DataFrame, ema_len: int = 21) -> pl.DataFrame:
    """Weekly frame where week t's state conditions week t+1's outcome.

    daily: [session, open, high, low, close]. Output columns per entry week t:
    week_end, close, ema, state (bull/bear at t), next_ret (close_{t+1}/close_t - 1),
    next_high_ret, next_low_ret (intraweek extremes of week t+1 vs close_t).
    Warmup weeks and the final (outcome-less) week are dropped.
    """
    wk = regime_frame(daily, RegimeConfig(ema_len=ema_len))
    wk = wk.with_columns(
        next_ret=pl.col("close").shift(-1) / pl.col("close") - 1.0,
        next_high_ret=pl.col("high").shift(-1) / pl.col("close") - 1.0,
        next_low_ret=pl.col("low").shift(-1) / pl.col("close") - 1.0,
        # 14-day (front_dte=14) variant: two-week horizon outcome vs entry
        next2_ret=pl.col("close").shift(-2) / pl.col("close") - 1.0,
        next2_high_ret=pl.max_horizontal(pl.col("high").shift(-1), pl.col("high").shift(-2))
        / pl.col("close")
        - 1.0,
        next2_low_ret=pl.min_horizontal(pl.col("low").shift(-1), pl.col("low").shift(-2))
        / pl.col("close")
        - 1.0,
    )
    return wk.filter(pl.col("state") != "warmup").drop_nulls("next_ret")


def dist_stats(rets: np.ndarray) -> dict:
    r = np.asarray(rets, dtype=np.float64)
    q = {f"p{p:02d}": float(np.percentile(r, p)) for p in PCTILES}
    m = r.mean()
    sd = r.std(ddof=1)
    skew = float(((r - m) ** 3).mean() / sd**3) if sd > 0 else float("nan")
    return {
        "n": len(r),
        "mean": float(m),
        "std": float(sd),
        "skew": skew,
        "frac_pos": float((r > 0).mean()),
        "min": float(r.min()),
        "max": float(r.max()),
        **q,
    }


def coverage_table(
    above: pl.DataFrame, q_grid: list[float] = Q_GRID, spot: float | None = None
) -> pl.DataFrame:
    """(b)+(e) core: per one-sided coverage q, the band edges of the above-EMA
    next-week return distribution, empirical stay-inside probability, and
    intraweek touch rates of each edge (from next week's daily highs/lows).

    Edge convention (§8.1): put edge at the (1-q) quantile, call edge at the
    q quantile; short strikes at spot x (1 + edge).
    """
    rets = above["next_ret"].to_numpy()
    next_low = above["next_low_ret"].to_numpy()
    next_high = above["next_high_ret"].to_numpy()
    rows = []
    for q in q_grid:
        put_edge = float(np.quantile(rets, 1.0 - q))
        call_edge = float(np.quantile(rets, q))
        inside = (rets > put_edge) & (rets < call_edge)
        touch_put = next_low <= put_edge
        touch_call = next_high >= call_edge
        row = {
            "q": q,
            "put_edge_ret": put_edge,
            "call_edge_ret": call_edge,
            "p_inside_close": float(inside.mean()),
            "p_touch_put": float(touch_put.mean()),
            "p_touch_call": float(touch_call.mean()),
            "p_touch_any": float((touch_put | touch_call).mean()),
        }
        if spot is not None:
            row["put_strike_dist_pts"] = abs(put_edge) * spot
            row["call_strike_dist_pts"] = call_edge * spot
        rows.append(row)
    return pl.DataFrame(rows)


def inverse_solve(
    p_win: float,
    win_pct_r: float = CLAIM_WIN_PCT_R,
    kelly: float = CLAIM_KELLY,
    ev_per_contract: float = CLAIM_EV_PER_CONTRACT,
) -> dict:
    """(c): given an empirical win probability p_win (from candle coverage) and
    the author's claims, solve for the loss profile his numbers REQUIRE.

    Binary-bet Kelly with win = +b*R and average loss = -a*R per unit risk R:
        f* = p/a - (1-p)/b
    Fixing b (win = +30% of R, i.e. credit kept) and f* = 0.60, the required
    average loss is  a = p / (f* + (1-p)/b).  EV as a fraction of R is then
    p*b - (1-p)*a, and the R per contract implied by EV = +$450/contract is
    450 / EV_frac.
    """
    b = win_pct_r
    a_req = p_win / (kelly + (1.0 - p_win) / b)
    ev_frac = p_win * b - (1.0 - p_win) * a_req
    return {
        "p_win": p_win,
        "required_avg_loss_pct_r": a_req,
        "ev_frac_of_r": ev_frac,
        "implied_r_per_contract": (ev_per_contract / ev_frac) if ev_frac > 0 else float("nan"),
        # sanity: with NO defense a full loss is (1 - b) of R
        "undefended_loss_pct_r": 1.0 - b,
    }


def losing_streaks(rets: np.ndarray, states: list[str], min_len: int = 3) -> list[dict]:
    """(d): runs of >= min_len consecutive negative weekly returns, with the
    regime state at the week BEFORE the run started (the entry-visible state)
    and the set of states during the run."""
    streaks: list[dict] = []
    run = 0
    start_idx = 0
    for i, r in enumerate(rets):
        if r < 0:
            if run == 0:
                start_idx = i
            run += 1
        else:
            if run >= min_len:
                streaks.append(_streak(states, start_idx, run))
            run = 0
    if run >= min_len:
        streaks.append(_streak(states, start_idx, run))
    return streaks


def _streak(states: list[str], start_idx: int, length: int) -> dict:
    during = states[start_idx : start_idx + length]
    return {
        "start_idx": start_idx,
        "length": length,
        "state_before": states[start_idx - 1] if start_idx > 0 else "none",
        "n_bear_during": sum(1 for s in during if s == "bear"),
        "all_bear_during": all(s == "bear" for s in during),
        "any_bull_during": any(s == "bull" for s in during),
    }


def coverage_14d(above: pl.DataFrame, q_grid: list[float]) -> pl.DataFrame:
    """(e) 14-day variant (PLAN §8.2 front_dte=14): band edges from the
    TWO-week above-EMA return distribution, touch rates from the two-week
    daily extremes. Same conventions as `coverage_table`."""
    sub = above.drop_nulls("next2_ret")
    rets2 = sub["next2_ret"].to_numpy()
    lo2 = sub["next2_low_ret"].to_numpy()
    hi2 = sub["next2_high_ret"].to_numpy()
    rows = []
    for q in q_grid:
        put_edge = float(np.quantile(rets2, 1.0 - q))
        call_edge = float(np.quantile(rets2, q))
        rows.append(
            {
                "q": q,
                "put_edge_ret": put_edge,
                "call_edge_ret": call_edge,
                "p_inside_close": float(((rets2 > put_edge) & (rets2 < call_edge)).mean()),
                "p_touch_put": float((lo2 <= put_edge).mean()),
                "p_touch_call": float((hi2 >= call_edge).mean()),
                "p_touch_any": float(((lo2 <= put_edge) | (hi2 >= call_edge)).mean()),
            }
        )
    return pl.DataFrame(rows)


def touch_calendar(above: pl.DataFrame, q_list: list[float]) -> pl.DataFrame:
    """(e): per-year counts of above-EMA entry weeks whose band edge was
    touched intraweek (next week's daily extremes) — the defense-activation
    calendar. Aggregate counts only; no raw rows."""
    rets = above["next_ret"].to_numpy()
    out = above.select(
        year=pl.col("week_end").dt.year(),
        next_low_ret=pl.col("next_low_ret"),
        next_high_ret=pl.col("next_high_ret"),
    )
    for q in q_list:
        put_edge = float(np.quantile(rets, 1.0 - q))
        call_edge = float(np.quantile(rets, q))
        out = out.with_columns(
            (pl.col("next_low_ret") <= put_edge).alias(f"touch_put_q{int(q * 100)}"),
            (pl.col("next_high_ret") >= call_edge).alias(f"touch_call_q{int(q * 100)}"),
        )
    agg = [pl.len().alias("n_entry_weeks")]
    for q in q_list:
        agg.append(pl.col(f"touch_put_q{int(q * 100)}").sum())
        agg.append(pl.col(f"touch_call_q{int(q * 100)}").sum())
    return out.group_by("year").agg(agg).sort("year")


# Mini-purchase spec (2026-08-14): regime-stratified sample Fridays for a
# cheap targeted options-data slice verifying item (c)'s open question —
# do real chains pay ~30%-of-risk credits at the (b)-table band edges?
# Windows: (name, start, end, rule) — "all" takes every week-end in range,
# "first_of_month" takes the first week-end of each listed month.
SPEC_WINDOWS: list[tuple[str, str, str, list[int] | None]] = [
    ("calm-2017", "2017-01-01", "2017-12-31", [1, 3, 5, 7, 9, 11]),
    ("volmageddon-feb-2018", "2018-01-26", "2018-02-28", None),
    ("covid-mar-2020", "2020-02-21", "2020-04-03", None),
    ("bear-2022", "2022-01-01", "2022-10-31", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
    ("vix-spike-aug-2024", "2024-07-26", "2024-08-23", None),
    ("live-window-2026", "2026-04-01", "2026-07-31", None),
]
SPEC_STRIKE_PAD = 0.04  # ±4% of spot: covers every (b) band edge (max ~2.8%) + wings
SPEC_BACK_DTE_MAX = 63  # front Friday + §8.1 long-leg offsets (+7..+56d) fit in 63d


def purchase_spec_rows(wk: pl.DataFrame) -> list[dict]:
    """Sample entry Fridays x strike ranges for the credit-check slice.

    wk: the weekly regime frame (week_end, close, state). week_end is the last
    trading day of each ISO week — the entry session. The front expiry is
    approximated by the NEXT week_end (the vendor slice should include the
    true holiday-shifted SPX/SPXW expiry dates around it).
    """
    rows = []
    week_ends = wk["week_end"].to_list()
    for name, start, end, months in SPEC_WINDOWS:
        lo = dt.date.fromisoformat(start)
        hi = dt.date.fromisoformat(end)
        seen_months: set[tuple[int, int]] = set()
        for i, we in enumerate(week_ends):
            if not (lo <= we <= hi):
                continue
            if months is not None:
                key = (we.year, we.month)
                if we.month not in months or key in seen_months:
                    continue
                seen_months.add(key)
            r = wk.row(i, named=True)
            spot = float(r["close"])
            front = week_ends[i + 1] if i + 1 < len(week_ends) else we + dt.timedelta(days=7)
            rows.append(
                {
                    "window": name,
                    "entry_friday": we,
                    "spot_close": spot,
                    "ema_state": r["state"],
                    "strike_lo": int(np.floor(spot * (1 - SPEC_STRIKE_PAD) / 5.0) * 5),
                    "strike_hi": int(np.ceil(spot * (1 + SPEC_STRIKE_PAD) / 5.0) * 5),
                    "front_expiry": front,
                    "back_expiry_max": front + dt.timedelta(days=SPEC_BACK_DTE_MAX - 7),
                }
            )
    return rows


def _purchase_spec_md(rows: list[dict]) -> list[str]:
    lines = [
        "## Mini-purchase specification (real-chain credit check at the (b) band edges)",
        "",
        "A cheap, targeted options-data slice (e.g. a CBOE DataShop custom order)",
        "answering item (c)'s open question BEFORE or alongside the full Pass-2",
        "purchase: what credits did real chains actually pay at the band-edge",
        "strikes, across vol regimes? The ±4% strike window covers every (b)-table",
        "edge (max ~2.8%) plus long wings, with margin for the ^GSPC-proxy-vs-SPX",
        "level difference. The Pass-1 v2 sweep found band strikes NEVER price as",
        "credits on the synthetic surface (0/4096) — this slice is the real-world",
        "test of that finding.",
        "",
        "**Evaluation semantics (2026-08-16 amendment — dual reading; the check",
        "MUST NOT hard-fail debit structures).** For every structure on every",
        "sample date, `eval/credit_check.py` reports BOTH: (a) signed net premium",
        "as % of risk (positive = credit), and (b) for debits, max-gain/risk at",
        'front expiry within the band and whether "+30% of R" is achievable there',
        "(the near-calendar reading — long-vega wings near the shorts make debits",
        "the structurally expected case). A near-ATM reference structure (shorts",
        "at / just outside spot) is priced on every sample date alongside the",
        'band-edge q-levels: his "big credit only happens if it is ATM or ITM"',
        "line makes that the direct Branch-B revenue measurement. Wing offsets",
        "sampled at {0, 25, 50} pts (0 = pure calendar) per the re-centered §8.1",
        "prior; front_dte 14 needs no extra data (expiries ≤ 63 DTE already",
        "cover it).",
        "",
        "**Per sample date, request:** SPX + SPXW quotes (NBBO bid/ask + sizes),",
        "EOD snapshot minimum (15:45-16:00 ET; a 10:00 ET snapshot is a cheap",
        "bonus), ALL listed expiries with DTE ≤ 63 calendar days (front Friday +",
        "every §8.1 back-leg offset), strikes within the table's range. Entry",
        "dates are the last trading day of each ISO week; expiry dates around",
        "holidays follow the CBOE shift convention — include the true listed",
        "expiry dates, not the approximations below.",
        "",
        "| window | entry Friday | spot (proxy close) | EMA state | strikes "
        "| front expiry ~ | back expiries thru |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['window']} | {r['entry_friday']} | {r['spot_close']:,.0f} "
            f"| {r['ema_state']} | {r['strike_lo']}-{r['strike_hi']} "
            f"| {r['front_expiry']} | {r['back_expiry_max']} |"
        )
    n = len(rows)
    lines += [
        "",
        f"{n} sample dates total (~a few thousand quote rows each at 5-pt strike",
        "spacing; the whole slice is well under a million rows). The 2026 live",
        "window rows are also part of the full Pass-2 fingerprint purchase — if",
        "the full purchase happens first, this slice is redundant for that window.",
        "",
    ]
    return lines


def _figures(
    above: pl.DataFrame, below: pl.DataFrame, cov: pl.DataFrame, fig_dir: Path
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    made = []

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(-0.12, 0.12, 61)
    ax.hist(above["next_ret"], bins=bins, alpha=0.6, density=True, label="above 21w EMA")
    ax.hist(below["next_ret"], bins=bins, alpha=0.6, density=True, label="below 21w EMA")
    ax.set_title("SPX next-week return conditional on 21-week EMA state (1999+, real candles)")
    ax.set_xlabel("next-week return")
    ax.legend()
    fig.tight_layout()
    p = fig_dir / "conditional_hist.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    made.append(str(p))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.plot(cov["q"], 100 * cov["put_edge_ret"].abs(), "o-", label="put edge |%|")
    ax1.plot(cov["q"], 100 * cov["call_edge_ret"], "s-", label="call edge %")
    ax1.set_xlabel("one-sided coverage q")
    ax1.set_ylabel("edge distance, % of spot")
    ax1.set_title("Coverage band edges (above-EMA weeks)")
    ax1.legend()
    ax2.plot(cov["q"], 100 * cov["p_touch_put"], "o-", label="touch put edge")
    ax2.plot(cov["q"], 100 * cov["p_touch_call"], "s-", label="touch call edge")
    ax2.plot(cov["q"], 100 * cov["p_touch_any"], "^-", label="touch either")
    ax2.set_xlabel("one-sided coverage q")
    ax2.set_ylabel("% of above-EMA weeks")
    ax2.set_title("Intraweek edge touches (defense activations)")
    ax2.legend()
    fig.tight_layout()
    p = fig_dir / "bands_and_touches.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    made.append(str(p))
    return made


def run_candle_study(
    free_root: str | Path = FREE_ROOT,
    out_md: str | Path = "reports/candle_study.md",
    ema_len: int = 21,
) -> dict:
    free_root = Path(free_root)
    manifest = json.loads((free_root / "manifest.json").read_text())
    daily = (
        pl.read_parquet(free_root / "gspc_daily.parquet")
        .rename({"date": "session"})
        .select("session", "open", "high", "low", "close")
        .sort("session")
    )

    wk_all = weekly_conditional_frame(daily, ema_len)
    wk = wk_all.filter(pl.col("week_end") >= pl.lit(STUDY_START).str.to_date())
    above = wk.filter(pl.col("state") == "bull")
    below = wk.filter(pl.col("state") == "bear")
    spot = float(daily["close"][-1])

    # (a) conditional distributions
    stats_above = dist_stats(above["next_ret"].to_numpy())
    stats_below = dist_stats(below["next_ret"].to_numpy())

    # (b) coverage bands + strike distances; stability by sub-period
    cov = coverage_table(above, Q_GRID, spot=spot)
    stability = subperiod_edges(above, q=0.90)

    # (c) inverse solve per q
    inv = pl.DataFrame(
        [{"q": r["q"], **inverse_solve(r["p_inside_close"])} for r in cov.iter_rows(named=True)]
    )
    # which q maps into his claimed WR band (close-outside = loss definition)
    wr_q = [
        r["q"]
        for r in cov.iter_rows(named=True)
        if CLAIM_WR_LO <= r["p_inside_close"] <= CLAIM_WR_HI
    ]

    # (d) losing streaks vs regime state (weekly own-return series, full frame)
    streak_frame = wk.with_columns(ret=pl.col("close").pct_change()).drop_nulls("ret")
    streaks = losing_streaks(
        streak_frame["ret"].to_numpy(), streak_frame["state"].to_list(), min_len=3
    )
    d_summary = {
        "n_streaks_ge3": len(streaks),
        "entered_in_bear": sum(1 for s in streaks if s["state_before"] == "bear"),
        "entered_in_bull": sum(1 for s in streaks if s["state_before"] == "bull"),
        "all_bear_during": sum(1 for s in streaks if s["all_bear_during"]),
        "any_bull_during": sum(1 for s in streaks if s["any_bull_during"]),
        "lengths": sorted(s["length"] for s in streaks),
    }

    # (e) defense-activation calendar
    cal = touch_calendar(above, [0.80, 0.85, 0.90, 0.95])
    cov14 = coverage_14d(above, [0.85, 0.90, 0.95])

    # VIX context on touch weeks (q=0.90), when the free VIX series is present
    vix_note = None
    vix_path = free_root / "vix_daily.parquet"
    if vix_path.exists():
        vix = pl.read_parquet(vix_path).select(pl.col("date"), vix_close=pl.col("close"))
        rets = above["next_ret"].to_numpy()
        pe, ce = float(np.quantile(rets, 0.10)), float(np.quantile(rets, 0.90))
        j = (
            above.with_columns(
                touched=(pl.col("next_low_ret") <= pe) | (pl.col("next_high_ret") >= ce)
            )
            .join(vix, left_on="week_end", right_on="date", how="left")
            .drop_nulls("vix_close")
        )
        vix_note = {
            "median_vix_touched": float(j.filter(pl.col("touched"))["vix_close"].median()),
            "median_vix_untouched": float(j.filter(~pl.col("touched"))["vix_close"].median()),
        }

    figures = _figures(above, below, cov, Path("reports/figures/candle_study"))

    results = {
        "label": "REAL FREE DAILY CANDLES — candles-only study; no options simulated",
        "sources": manifest["series"],
        "study_window": [str(wk["week_end"].min()), str(wk["week_end"].max())],
        "ema_len": ema_len,
        "n_weeks": wk.height,
        "n_above": above.height,
        "n_below": below.height,
        "a_dist_above": stats_above,
        "a_dist_below": stats_below,
        "b_coverage": cov.to_dicts(),
        "b_stability_q90": stability.to_dicts(),
        "c_inverse_solve": inv.to_dicts(),
        "c_q_matching_claimed_wr": wr_q,
        "d_streaks": d_summary,
        "e_touch_calendar": cal.to_dicts(),
        "e_coverage_14d": cov14.to_dicts(),
        "vix_context_q90": vix_note,
        # mini-purchase spec uses the FULL weekly frame (spec windows predate
        # nothing — 2017+ is inside the study window, but keep wk for states)
        "f_purchase_spec": purchase_spec_rows(wk),
        "figures": figures,
    }

    out = Path(out_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_report_md(results, spot))
    out.with_suffix(".json").write_text(json.dumps(results, indent=2, default=str))
    return results


def _report_md(res: dict, spot: float) -> str:
    a_ab, a_be = res["a_dist_above"], res["a_dist_below"]
    lines = [
        "# Candle study — replication of the author's ENTIRE backtest (REAL daily candles)",
        "",
        "**CANDLES-ONLY.** Real free daily SPX data; an explicit user-approved exception",
        "to Pass 1's synthetic-only rule (PLAN §12.0). Per the author's 2026-08-10",
        'disclosure, his full backtest was: "SPX% return weekly above 21 EMA to estimate',
        'historical EV" plus static credit pricing from a ~$500 options-data slice.',
        "This study replicates that process. **No options positions are simulated and",
        "no claim is made about the options strategy itself.** Not investment advice.",
        "",
        "## Data sources (all free; raw files gitignored, never committed)",
        "",
    ]
    for s in res["sources"]:
        lines.append(
            f"- {s['name']}: `{s['source']}` ({s['rows']} rows, {s['date_min']} → {s['date_max']})"
        )
    lines += [
        "",
        f"Study window {res['study_window'][0]} → {res['study_window'][1]} "
        f"({res['n_weeks']} completed weeks; EMA warm-up from 1995). "
        f"State at week t's Friday close conditions week t+1's outcome (no lookahead).",
        "",
        "## (a) Conditional next-week return distributions (21-week EMA)",
        "",
        "| | above EMA | below EMA |",
        "|---|---|---|",
        f"| n weeks | {a_ab['n']} | {a_be['n']} |",
        f"| mean | {a_ab['mean']:.4%} | {a_be['mean']:.4%} |",
        f"| std | {a_ab['std']:.4%} | {a_be['std']:.4%} |",
        f"| skew | {a_ab['skew']:.2f} | {a_be['skew']:.2f} |",
        f"| % positive | {a_ab['frac_pos']:.1%} | {a_be['frac_pos']:.1%} |",
        f"| p05 / p95 | {a_ab['p05']:.2%} / {a_ab['p95']:.2%} "
        f"| {a_be['p05']:.2%} / {a_be['p95']:.2%} |",
        f"| p01 / p99 | {a_ab['p01']:.2%} / {a_ab['p99']:.2%} "
        f"| {a_be['p01']:.2%} / {a_be['p99']:.2%} |",
        f"| min / max | {a_ab['min']:.2%} / {a_ab['max']:.2%} "
        f"| {a_be['min']:.2%} / {a_be['max']:.2%} |",
        "",
        "![conditional distributions](figures/candle_study/conditional_hist.png)",
        "",
        "## (b) Implied coverage bands and strike distances (feeds §8.1 percentile family)",
        "",
        "Edges are quantiles of the ABOVE-EMA next-week return distribution; strike",
        f"distances shown at the latest close (SPX ≈ {spot:,.0f}).",
        "",
        "| q | put edge | call edge | put dist (pts) | call dist (pts) "
        "| P(close inside) | P(touch put) | P(touch call) | P(touch any) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res["b_coverage"]:
        lines.append(
            f"| {r['q']:.2f} | {r['put_edge_ret']:.2%} | {r['call_edge_ret']:.2%} "
            f"| {r['put_strike_dist_pts']:.0f} | {r['call_strike_dist_pts']:.0f} "
            f"| {r['p_inside_close']:.1%} | {r['p_touch_put']:.1%} "
            f"| {r['p_touch_call']:.1%} | {r['p_touch_any']:.1%} |"
        )
    lines += [
        "",
        "Sub-period stability of the q=0.90 edges (regime dependence of the band):",
        "",
        "| period | n | put edge | call edge |",
        "|---|---|---|---|",
    ]
    for r in res["b_stability_q90"]:
        lines.append(
            f"| {r['period']} | {r['n']} | {r['put_edge_ret']:.2%} | {r['call_edge_ret']:.2%} |"
        )
    lines += [
        "",
        "![bands and touches](figures/candle_study/bands_and_touches.png)",
        "",
        "## (c) Inverse solve on his claims (Kelly ~60%, win ~+30% of R, EV ~+$450/contract)",
        "",
        "Given the empirical win probability p(q) = P(close inside band | above EMA),",
        "binary-bet Kelly f* = p/a - (1-p)/b with win b = +30% of R fixed by his claim.",
        "Solving f* = 0.60 for the required average loss a, then EV/R and the R per",
        "contract implied by EV = +$450:",
        "",
        "| q | p(win) | required avg loss (%R) | EV (%R) "
        "| implied R/contract | undefended loss (%R) |",
        "|---|---|---|---|---|---|",
    ]
    for r in res["c_inverse_solve"]:
        lines.append(
            f"| {r['q']:.2f} | {r['p_win']:.1%} | {r['required_avg_loss_pct_r']:.1%} "
            f"| {r['ev_frac_of_r']:.2%} | ${r['implied_r_per_contract']:,.0f} "
            f"| {r['undefended_loss_pct_r']:.0%} |"
        )
    wr_q = res["c_q_matching_claimed_wr"]
    lines += [
        "",
        f"- q whose close-based win rate lands in his claimed WR band "
        f"[{CLAIM_WR_LO:.0%}, {CLAIM_WR_HI:.0%}]: "
        + (
            ", ".join(f"{q:.2f}" for q in wr_q)
            if wr_q
            else "**none in the [0.80, 0.95] grid** — his claimed WR requires q > 0.92 "
            "(two-sided close-based wins ~ 2q-1), or losses defined by touch+defense "
            "rather than close-outside"
        ),
        "- **Plausibility:** a win of +30% of R means the credit ≈ 30% of risk, matching",
        "  his own quoted credit thresholds (30% typical). The table shows what the",
        "  DEFENSE must accomplish: cut the average realized loss from the undefended",
        "  70% of R down to the 'required avg loss' column. Whether real SPX chains",
        "  actually offered ~30%-of-risk credits at these strike distances is exactly",
        "  what Pass 2 options data verifies — candles cannot.",
        "",
        '## (d) "3 consecutive bad weeks happen below the EMA" — verify/refute',
        "",
        "- losing streaks of ≥3 consecutive negative weeks: "
        f"**{res['d_streaks']['n_streaks_ge3']}**",
        f"- entered (state the week before the streak began) in BEAR: "
        f"**{res['d_streaks']['entered_in_bear']}**, "
        f"in BULL: **{res['d_streaks']['entered_in_bull']}**",
        f"- every week of the streak below EMA: {res['d_streaks']['all_bear_during']}; "
        f"streaks touching a bull week: {res['d_streaks']['any_bull_during']}",
        f"- streak lengths: {res['d_streaks']['lengths']}",
        "",
        "## (e) Defense-activation calendar (intraweek edge touches, above-EMA entry weeks)",
        "",
        "Counts of entry weeks per year whose next-week daily extremes touched the",
        "band edge (put / call), by coverage q:",
        "",
        "| year | entries | put q80 | call q80 | put q85 | call q85 "
        "| put q90 | call q90 | put q95 | call q95 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res["e_touch_calendar"]:
        lines.append(
            f"| {r['year']} | {r['n_entry_weeks']} "
            f"| {r['touch_put_q80']} | {r['touch_call_q80']} "
            f"| {r['touch_put_q85']} | {r['touch_call_q85']} "
            f"| {r['touch_put_q90']} | {r['touch_call_q90']} "
            f"| {r['touch_put_q95']} | {r['touch_call_q95']} |"
        )
    if res["vix_context_q90"]:
        v = res["vix_context_q90"]
        lines += [
            "",
            f"VIX context (q=0.90): median entry-week VIX close {v['median_vix_touched']:.1f} "
            f"when the next week touched an edge vs {v['median_vix_untouched']:.1f} when it "
            "did not — defense weeks cluster in elevated-vol tape.",
        ]
    lines += [
        "",
        "### 14-day variant (front_dte=14, PLAN §8.2 2026-08-16 amendment)",
        "",
        "Band edges from the TWO-week above-EMA return distribution; touch rates",
        "over the two-week daily extremes:",
        "",
        "| q | put edge | call edge | P(close inside) "
        "| P(touch put) | P(touch call) | P(touch any) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in res["e_coverage_14d"]:
        lines.append(
            f"| {r['q']:.2f} | {r['put_edge_ret']:.2%} | {r['call_edge_ret']:.2%} "
            f"| {r['p_inside_close']:.1%} | {r['p_touch_put']:.1%} "
            f"| {r['p_touch_call']:.1%} | {r['p_touch_any']:.1%} |"
        )
    lines += ["", *_purchase_spec_md(res["f_purchase_spec"])]
    lines += [
        "",
        "---",
        "",
        "**Reminder:** this replicates the author's candle methodology. It validates or",
        "refutes what CAN be known from candles; the options strategy's evidential base",
        "remains ~6 months paper + ~4 months live (PLAN §1.7). Not investment advice.",
        "",
    ]
    return "\n".join(lines)


def subperiod_edges(above: pl.DataFrame, q: float) -> pl.DataFrame:
    """Stability check for (b): band edges re-estimated per sub-period."""
    df = above.with_columns(
        period=pl.when(pl.col("week_end") < pl.date(2008, 1, 1))
        .then(pl.lit("1999-2007"))
        .when(pl.col("week_end") < pl.date(2017, 1, 1))
        .then(pl.lit("2008-2016"))
        .otherwise(pl.lit("2017-now"))
    )
    rows = []
    for period, grp in df.group_by("period", maintain_order=True):
        r = grp["next_ret"].to_numpy()
        rows.append(
            {
                "period": period[0],
                "n": len(r),
                "put_edge_ret": float(np.quantile(r, 1.0 - q)),
                "call_edge_ret": float(np.quantile(r, q)),
            }
        )
    return pl.DataFrame(rows).sort("period")


def main() -> None:
    import hashlib

    from options_strategy import ledger

    res = run_candle_study()
    manifest = json.loads((FREE_ROOT / "manifest.json").read_text())
    study_cfg = json.dumps(
        {"study": "candle_replication", "ema_len": res["ema_len"], "q_grid": Q_GRID},
        sort_keys=True,
        separators=(",", ":"),
    )
    ledger.append(
        [
            ledger.LedgerRow(
                kind="study",
                config_hash=hashlib.sha256(study_cfg.encode("ascii")).hexdigest(),
                git_sha=ledger.current_git_sha(),
                data_version=f"freedata-{manifest['fetched_at_utc'][:10]}",
                seed=0,
                metrics={
                    "n_weeks": res["n_weeks"],
                    "n_above": res["n_above"],
                    "n_streaks_ge3": res["d_streaks"]["n_streaks_ge3"],
                    "streaks_entered_bear": res["d_streaks"]["entered_in_bear"],
                },
                artifacts=["reports/candle_study.md"],
            )
        ]
    )
    print(json.dumps({k: res[k] for k in ("study_window", "n_weeks", "n_above", "n_below")}))


if __name__ == "__main__":
    main()
