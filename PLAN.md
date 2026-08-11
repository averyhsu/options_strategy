# PROJECT PLAN — `options_strategy`
## SPX Double-Diagonal Backtesting Engine, Parameter Identification & Robustness Evaluation

> **How to use this file:** Commit it as **`PLAN.md`** in the repo root, alongside the slim **`CLAUDE.md`** that Claude Code auto-loads every session. This plan is the source of truth for scope, phases, and acceptance criteria; Claude Code reads it in full at kickoff and re-reads the current phase's section each time the loop re-enters ENGINEER. **Execution is autonomous loop mode (§12.0):** phases run strictly in order but continuously — ENGINEER → GENERATE → VALIDATE → TEST — advancing on machine-verified green acceptance criteria without waiting for human review, until P6 completes. Do not skip phases or acceptance criteria. Do not copy this plan's content into CLAUDE.md — it is deliberately kept out of the always-loaded context.

---

## 0. Mission

Build a research-grade backtesting and strategy-identification system for a family of **SPX weekly double-diagonal option strategies** reverse-engineered from a public trader's disclosures. The system must:

1. **Simulate** the strategy family with realistic execution: NBBO-aware fills, resting limit orders, slippage, IBKR-style fees, margin/risk-based sizing, correct SPX/SPXW settlement.
2. **Validate** itself against hard invariants (cash conservation, put-call parity, no-lookahead, settlement math, golden strategies).
3. **Sweep** the undisclosed parameter space (strikes/deltas, long-leg DTE, entry EV thresholds, regime rules, defense policy) — coarse EOD prune → intraday refinement.
4. **Identify** which parameter regions are consistent with the trader's published performance fingerprints (approximate Bayesian computation over summary statistics), reporting identifiability honestly.
5. **Evaluate** whether the strategy family has robust positive expectancy after costs across 2016–2026, with walk-forward analysis, deflated Sharpe ratio, probability of backtest overfitting, and stress tests.

**Non-goals:** live trading, order routing, broker integration, real-time data, ML signal discovery, multi-underlying support. The trader's exploratory 0DTE and futures side-projects are entirely out of scope — this project models the weekly SPX double-diagonal strategy only.

**Prime directive:** correctness before speed, and honesty before flattering results. A result that says "not identifiable" or "no edge after costs" is a successful outcome.

---

## 1. Background: the target strategy dossier

Source: a Reddit r/algotrading post (July 2026) plus the author's comment replies, and three IBKR app screenshots. Every claim is tagged: **[stated]** = author said it, **[derived]** = follows from math on his statements, **[assumed]** = our prior, must remain sweepable.

### 1.1 Structure & cadence
- Underlying: **SPX options exclusively** (cash-settled, European). [stated]
- Cadence: **one trade per week**, opened on Friday ("Friday to Friday"), short legs expiring the following Friday. [stated]
- Structure: **double diagonal** — short front-week call + short front-week put, long further-dated call + put wings. [stated: "It opens a double diagonal"]
- Greek profile: **theta-positive, short gamma, net long vega** ("short but long vega so I benefit from DD"). [stated] Long vega ⇒ back-month long legs dominate vega. [derived]
- Position left alone until **the day before expiration**, except defense "if any of the sides get touched — that is where the edge shines." [stated; exact trigger/action undisclosed]
- Hold to expiry or manage T−1; ambiguity between "manage T−1 only" and "act on touch" ⇒ **defense timing is a sweep dimension**. [assumed]

### 1.2 Signal / regime filter
- **21-period EMA on weekly SPX closes** as bull/bear regime separator. [stated]
- Three tradeable events: **crossover, rejection, retracement** (retracement = highest-EV, rarest). [stated]
- Function of filter per author: historical 3-losing-week clusters occurred "when SPX was already below the 21EMA" ⇒ filter primarily avoids bear regimes. [stated]
- Formal event definitions are NOT disclosed ⇒ parameterize (§8.3). [assumed]

### 1.3 Entry mechanism
- Not fixed-delta-on-a-schedule. **Resting limit orders priced at historical-EV thresholds**; they fire automatically when credit ≥ threshold (e.g., "only open the spread if the gain is 50% of the width, and that only happens if it is ATM or ITM or maybe open for further dte"). [stated]
- "No trade this week" is acceptable ("wouldn't be surprised if some weeks I sit aside"), though live sample filled every week. [stated]
- ⇒ The engine MUST support **resting combo limit orders with a fill-probability model**, not just market-on-signal. This is a core requirement, not an extra.

### 1.4 Sizing & payoff economics
- Backtested Kelly ≈ 60%; trades **quarter-Kelly = 15% of NAV at risk per weekly cycle**. [stated]
- Winning weeks pay **≈ +30% of risk** ("300 dollars per 1000 at risk") ⇒ ≈ +4.5% NAV per winning week; author rounds to "~5% weekly." [stated]
- Kelly inversion with b = 0.30, f* = 0.60 ⇒ implied win probability **p ≈ 0.91**. Breakeven at b = 0.30 is p ≈ 0.77. [derived]
- BUT his stress-test numbers imply typical losing weeks ≈ **−25 to −30% of risk** (3-week nightmare ≈ −12% NAV total ⇒ ≈ −4% NAV/week ⇒ ≈ −27% of the 15% risked). Under win +0.3R / loss −0.27R the Kelly arithmetic he quotes doesn't cleanly reproduce ⇒ his "risk"/Kelly language is muddled. **Treat weekly loss magnitude as a free parameter** with prior: typical loss −20%..−40% of R, tail loss −70%..−100% of R (gap events; his live 1-day DD of −11.11% NAV ≈ −74% of R supports the tail). [derived/assumed]
- Claimed EV ≈ **+$450 per contract** opened. Weak constraint; use only as a sanity band on per-contract economics. [stated]

### 1.5 Costs (author's own numbers — calibrate defaults to these)
- Fees ≈ **$1.60 per leg** all-in at IBKR. [stated]
- Slippage ≈ **$5–10 per spread**. [stated]
- Backtest inputs: bought CBOE historical options data (~$500); SPX candles from IBKR gateway. [stated]

### 1.6 Track record & claims
- Backtest "26 years." Can only be the **EMA regime study on candles** — dense SPX weekly chains don't exist for 26 years. The options overlay was necessarily validated on a much shorter window. [derived]
- **2026-08-10 disclosure (author, pressed for OOS):** there are none — "no OOS results since the strat is too complex to model due to long vega"; daily chain data would have cost ~$10k. [stated]
- **The backtest was candles-only:** "Backtest consisted of SPX% return weekly above 21 EMA to estimate historical EV" — conditional weekly SPX return distributions above/below the 21-week EMA. The options structure itself (long-vega wing marking, mid-week paths, touch-defense) was **never simulated**. [stated/derived]
- The ~$500 CBOE data purchase was used **only to price typical spread credits** (a static credit study on one small slice). Kelly ~60%, ~90% WR, and EV ~+$450/contract all derive from that static candle+credit study. [stated/derived]
- "MaxDD total **-11%**" per the author; he manually front-tests before deploying. [stated]
- Evidential base for the full strategy as actually traded: **~6 months paper + ~4 months live**. [derived]
- Paper traded **Oct 2025 – Mar 2026**; live money from **April 2026**. [stated]
- Live window analyzed here: **2026-04-01 → 2026-07-30**. [screenshots]
- **Identification prior (2026-08-10):** short strikes were almost certainly placed at **percentiles of the above-EMA weekly-return distribution** (a candle-derived coverage band), not at option-market deltas — that is the only strike-placement rule his stated backtest could have produced. Encoded as the default strike family in §8.1. [derived]

### 1.7 Known credibility caveats (keep in the final report)
- **No out-of-sample results, by the author's own admission** (2026-08-10 disclosure): the strategy as traded was never backtested, only the candle-conditional EV study.
- **The defense — the component he calls the edge — was never backtested or simulated at all**; it exists only in ~6 months of paper trading + ~4 months live. The final report MUST state that the strategy's evidential base is ~6 months paper + ~4 months live.
- Credits/EV were estimated from one ~$500 options-data slice, likely covering a **single vol regime** — the +$450/contract EV and Kelly ~60% inherit that regime's pricing.
- Daily-candle backtests cannot validate an intraday touch-defense — the exact component he credits for the edge.
- Live max DD (11.11%) already ≈ his modeled worst case (~12%): realized variance runs at model ceiling.
- Net Sharpe ~3 on ~87 daily observations has enormous error bars (Lo 2002 — a paper he himself cited).
- 3 profitable months of short-gamma carry in a friendly regime cannot distinguish "edge" from "tail not yet met."

---

## 2. Fingerprint targets (ground truth to match)

From IBKR PortfolioAnalyst screenshots, window **2026-04-01 → 2026-07-30**, 87 trading days:

| # | Metric | Value | Notes |
|---|--------|-------|-------|
| F1 | Ending VAMI (base 1000) | **1,460.91** | ⇒ +46.09% cumulative over window |
| F2 | Rolling 3M return (app home) | +41.26% | different (rolling) window; secondary target |
| F3 | Max drawdown | **11.11%** | close-to-close on daily VAMI |
| F4 | DD peak → valley dates | **2026-07-10 (Fri) → 2026-07-13 (Mon)** | single weekend+Monday event — strongest structural constraint |
| F5 | Recovery | 9 days | trading days back to prior peak |
| F6 | Sharpe (ann.) | **2.99** | IBKR definition, see §2.1 |
| F7 | Sortino (ann.) | **4.45** | |
| F8 | Std dev (daily) | **2.44%** | |
| F9 | Downside deviation (daily) | **1.64%** | |
| F10 | Mean daily return | **0.47%** | arithmetic |
| F11 | Positive periods | 63 (72.41%) | days with r > 0 |
| F12 | Negative periods | 24 (27.59%) | |
| F13 | Weekly cadence | entries Fri; short legs SPXW PM next Fri | |
| F14 | Weekly win profile | wins ≈ +30% of R (R = 15% NAV); WR prior ≈ 0.85–0.92 | from §1.4 |

### 2.1 Metric self-consistency (bake these into unit tests of `eval/metrics_ibkr.py`)
These all check out, which means the screenshots are internally honest and our metric definitions can be pinned:

- **Compounding:** geometric mean ≈ 0.47% − (2.44%)²/2 ≈ 0.44%/day ⇒ 1.0044⁸⁷ ≈ 1.466 ≈ VAMI 1460.91 ✓
- **Risk-free calibration:** with daily rf ≈ 0.0104% (≈ **2.62%/yr**):
  - Sharpe = (0.47 − 0.0104)/2.44 × √252 = **2.990** ✓
  - Sortino = (0.47 − 0.0104)/1.64 × √252 = **4.449** ✓
  - The SAME rf reproduces both ⇒ implement Sharpe/Sortino as excess-over-rf with configurable rf; default the 2026 sim window's rf to the T-bill curve and verify it lands near 2.6%.
- **Counts:** 63 + 24 = 87 trading days; %positive = 63/87 = 72.41% ✓

**Implement metrics to IBKR conventions:** daily time-weighted returns (no external flows in sim, so TWR = NAV return), VAMI base 1000, annualization √252, max DD on close-to-close VAMI, Sortino downside deviation vs rf floor. Golden test: feed a synthetic series with exactly mean 0.47%/σ 2.44%/dd 1.64% and assert 2.99/4.45 outputs at rf = 2.62%.

---

## 3. System architecture

Two-track engine sharing one strategy definition:

```
                    ┌──────────────────────────────────────────┐
                    │        strategy definition (config)      │
                    └───────────────┬──────────────────────────┘
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
  TRACK A: vectorized EOD                        TRACK B: event-driven intraday
  (polars; fast; coarse sweep,                   (1-min bars; resting-order fills,
   pruning, 26y regime studies)                   touch-defense, settlement ticks)
            └───────────────────────┬───────────────────────┘
                                    ▼
                 shared: pricing, fees, margin, portfolio,
                 settlement, metrics, ledger, reporting
```

**Consistency requirement:** for strategies expressible at EOD granularity (no touch-defense, fills at close-mid), Track A and Track B must agree on final NAV within 1e-6 relative. This is an integration test, not a hope.

### 3.1 Repo layout

```
options_strategy/
  CLAUDE.md                    # this file
  ASSUMPTIONS.md               # living log of every modeling assumption
  pyproject.toml               # pip-installed into the `options_strategy` conda env; python 3.12
  configs/
    base.yaml                  # engine defaults (fees, fill model, rf source)
    spaces/                    # sweep space definitions
    experiments/               # frozen configs of noteworthy runs
  src/options_strategy/
    data/                      # loaders, schemas, QA, synthetic generator, calendar
    pricing/                   # forwards, IV solver, greeks, settlement values
    engine/                    # events, clock, portfolio, fills, fees, margin
    strategy/                  # regime, diagonal builder, entry, defense, sizing
    sweep/                     # spaces, runners (LHS/Sobol), optuna, ABC matcher
    eval/                      # metrics_ibkr, tearsheet, stress, walkforward, dsr_pbo
    cli.py                     # options_strategy qa|run|sweep|match|report
  tests/
    unit/  integration/  golden/  property/
  experiments/ledger.parquet   # run_id, config_hash, git_sha, data_version, seed, metrics
  notebooks/
```

### 3.2 Stack
- Python 3.12, **miniconda env** `options_strategy` for env (user directive 2026-08-06 — replaces uv; deps in pyproject, installed via pip), **polars** primary dataframes (pandas allowed at edges), numpy, **numba** for hot loops only after profiling.
- IV: `py_vollib_vectorized` (Jäckel) OR in-house vectorized Newton with Corrado-Miller seeds — pick one, test round-trip ≤ 1e-6.
- Sweep: Sobol/LHS via `scipy.stats.qmc`; refinement via **optuna** (TPE) used to *characterize regions*, never to crown a single point.
- Parallelism: `joblib`/`concurrent.futures` first; ray only if needed.
- Config: pydantic-settings + YAML; every run logs `config_hash` + `git_sha` + `data_version` + `seed` to the ledger. Identical config+seed ⇒ bit-identical results (test this).
- Calendar: `exchange_calendars` (XCBOE) + an **expirations override table built from the actual data** (trust listed expiries in data over synthetic rules).
- Tooling: ruff, pytest (+ pytest-xdist), hypothesis for property tests, mypy on `pricing/` and `engine/` at minimum.

---

## 4. Data contracts

The user is purchasing intraday options data (vendor TBD: Theta Data / CBOE DataShop / Polygon). Build **vendor adapters → one internal schema**. Develop everything against the synthetic generator (§5) so real data is a drop-in.

### 4.1 Internal schemas (parquet, partitioned by trade_date / expiry)

**`option_quotes`** (1-min NBBO bars minimum; finer if available)
```
ts (ET, tz-aware) | root (SPX|SPXW) | expiry_date | am_pm_settle | strike | cp |
bid | ask | bid_size | ask_size | last | volume | open_interest (EOD join) | quote_condition
```

**`underlying_bars`** (1-min SPX index + daily; plus ES front-month optional for overnight context)
```
ts | open | high | low | close | (volume for ES only)
```

**`rates`**: daily SOFR/T-bill curve → rf(t, T) for discounting and metric rf.
**`calendar`**: sessions, early closes, holidays, and the **observed expiry list per root** (with AM/PM flag; note holiday-shifted expirations, e.g., Good-Friday weeks).
**`settlement_values`**: official SPXW PM settlement (index close print) and SPX AM settlement (SET / Special Opening Quotation) where applicable. If vendor doesn't supply SET, reconstruct PM from the 4:00pm ET index close and flag AM-settled monthlies as requiring the official value.

### 4.2 Data QA gate (`options_strategy qa`) — run before anything touches the data
Per snapshot/expiry:
1. **Put-call parity / forward extraction:** regress C − P on K ⇒ slope ≈ −DF, intercept ⇒ F. Flag snapshots with parity residual RMSE above tolerance. (This doubles as the forward curve used by pricing.)
2. Crossed/locked markets, zero/negative widths, stale quotes (unchanged > N min during RTH), bid > theoretical bounds.
3. Monotonicity & convexity in strike (butterfly arb flags), calendar monotonicity.
4. Tick-size conformity (SPX: $0.05 below $3 premium, $0.10 above — verify against data, don't hardcode blindly).
5. Coverage report: strikes/expiries per day vs expected; missing minutes; volume sanity.
Output: HTML/markdown QA report + a `quality_flags` column consumed by the fill model (never fill against flagged quotes).

### 4.3 Historical range guidance (for the user's purchase; put in report too)
- **Intraday options:** 2016-01 → present minimum (covers Volmageddon '18, Dec '18, COVID '20, '22 bear grind, Aug-2024 VIX spike, and the 2026 live window for fingerprint matching). 2012+ if budget allows.
- **EOD options:** 2005 → present if cheap (weeklies era).
- **SPX daily candles:** 1999 → present (free) for the 26-year regime replication.
- Note: SPXW daily (Tue/Thu) expirations only exist from ~mid-2022; before that M/W/F. The engine must only trade expiries that actually existed on a given date — enforce via the observed-expiry table.

---

## 5. Synthetic data generator (build FIRST — unblocks everything)

`options_strategy.data.synthetic` — deterministic, seeded world generator so the whole stack is developed and tested before purchased data lands.

- Underlying: **Heston + Merton jumps** (params in config; defaults loosely SPX-like: v0/θ ≈ 0.03, κ ≈ 2, ξ ≈ 0.5, ρ ≈ −0.7, jump λ ≈ 0.5/yr, mean −3%, σ 4%). 1-min paths with overnight gaps (separate overnight variance + occasional weekend jump injection — needed to rehearse the F4 fingerprint).
- Chains: strikes in 5-pt spacing near ATM widening to 25-pt in wings; expiries per the era-correct listing rules; prices from Heston characteristic function (or BSM on a parametric SVI surface fitted per slice — simpler and fine); IVs self-consistent with pricing.
- Microstructure: NBBO width model = f(moneyness, DTE, vol level) with floors at tick size; size model; stale-quote and crossed-quote injection at configurable rates (to exercise QA); quote_condition codes.
- Regimes: script multi-year scenarios (grind-up, crash, chop) to unit-test the EMA module against known truth.
- Must pass its own QA gate (§4.2) except the deliberately injected defects.

**Acceptance:** `options_strategy qa` on synthetic world ⇒ clean report; parity-extracted forwards match the generator's true forwards within tolerance.

---

## 6. Pricing layer (`options_strategy.pricing`)

- **Model:** Black-76 on the parity-extracted forward per expiry (avoids dividend modeling entirely). Discounting off the rates curve.
- **IV solver:** vectorized, round-trip |price(iv(p)) − p| ≤ 1e-6 across a strike/DTE/vol grid (golden test). Handle deep-ITM via put-call parity rotation.
- **Greeks:** delta, gamma, theta, vega, vanna/volga optional. Analytic Black-76.
- **Settlement:** `settle_value(root, expiry, cp, strike)` — SPXW: PM (official close print); SPX monthlies: AM (SET). Expiring options convert to cash at settlement; NO exercise/assignment mechanics (European cash-settled). Unit tests with hand-computed examples, including an ITM short call over a settlement print and a holiday-shifted expiry.
- **Marking:** positions MTM at NBBO mid when quotes are sane, else model price with a `marked_from_model` flag; daily NAV uses 4:00pm ET marks (IBKR-like).
- **Vol dynamics assumption for scenario risk (§7.4):** sticky-strike default; sticky-delta as config alternative. Log choice in ASSUMPTIONS.md.

---

## 7. Execution & portfolio engine (`options_strategy.engine`)

### 7.1 Event core (Track B)
Clock ticks 1-min bars (ET, exchange calendar). Event types: `BarEvent`, `OrderEvent`, `FillEvent`, `SettlementEvent`, `MarkEvent (EOD)`. Strategy code receives ONLY a `MarketView` facade (§11 no-lookahead).

### 7.2 Orders & fills — the critical component
Support: market, limit, **resting multi-leg combo limit (GTC intra-week)**, cancel/replace.

Combo NBBO from leg NBBOs (credit combo: bid = Σ short-leg bids − Σ long-leg asks, etc.). Fill logic for a resting credit order at limit `c*`, three switchable models (ALL runs report at least CONSERVATIVE and MID as bounds):

| Model | Fill rule for resting orders | Use |
|---|---|---|
| CONSERVATIVE | combo market **crosses through** c* (opposite side ≥ c*) and persists ≥ 1 full bar; fill at c* | lower bound / headline results |
| MID | combo mid ≥ c* + concession k·(combo half-spread), k default calibrated so per-spread cost ≈ $5–10 (his number) | central case |
| OPTIMISTIC | touch fills (mid ≥ c* momentarily) | upper bound only; never headline |

Defensive/closing orders that must execute now: fill at mid ∓ k_exit·half-spread per leg, k_exit default 1.0 (full cross), sweepable. Reject fills against quality-flagged quotes; cap fill size vs displayed size × participation factor (default 25%) — flag configs whose implied size exceeds book depth (§13, capacity note).

### 7.3 Fees
Config table, per contract per leg: `commission + exchange_fee + clearing + regulatory`. **Default calibrated to ≈ $1.60/leg all-in** (author's IBKR number); expose components so the user can true-up against a real IBKR statement. Fee sensitivity multiplier ×1..×3 in evaluation.

### 7.4 Margin & risk-based sizing
"15% of NAV at risk" needs an operational definition. Implement THREE, sweepable (§8.5):
- **R_scenario** (default): max loss at front expiry over grid S ∈ ±12% (0.5% steps) × vol shift ∈ {−30%, 0, +30%} relative, back legs revalued under the §6 vol-dynamics assumption. n = ⌊0.15·NAV / R⌋.
- **R_width:** distance-based proxy (short-strike width + net debit style approximations).
- **R_margin:** Reg-T-ish spread margin approximation as constraint & alternative denominator.
Portfolio tracks cash, positions, accrued fees; **invariant: cash + Σ MTM = NAV** every mark (test).

### 7.5 Track A (vectorized EOD)
Same strategy config compiled to daily-close logic: entries at close-mid when signal + credit threshold met on EOD chain; no touch-defense (or a crude close-based proxy variant for pruning only); settlement at official values. Purpose: 26-y regime studies on candles + 10⁴–10⁵-config pruning on EOD options.

---

## 8. Strategy family (`options_strategy.strategy`) — the parameter space

Everything below is a config field. Ranges = sweep priors.

### 8.1 Structure

**Strike-placement families (2026-08-10 amendment, per the §1.6 disclosure):** the **DEFAULT family is percentile-band placement** — short strikes at percentiles of the trailing above-EMA weekly-return distribution (candle-derived coverage band), because that is the only rule his stated backtest could have produced. Two-sided coverage q ∈ [0.80, 0.95]; asymmetric tails allowed (q_put ≠ q_call); short strikes at spot × (1 + band edge). Free-delta placement (table below) remains the **fallback family**. If the percentile family matches the fingerprints and free-delta adds no fit, that is itself evidence about his process.

| Param | Range / options | Prior center |
|---|---|---|
| strike_family | **percentile-band (default)** / free-delta (fallback) | percentile-band |
| coverage_q_put | 0.80–0.95 (one-sided put coverage of trailing above-EMA weekly-return dist) | 0.85–0.92 |
| coverage_q_call | 0.80–0.95 (asymmetric allowed) | 0.85–0.92 |
| short_put_delta | 5–50Δ (free-delta family only) | 15–30Δ |
| short_call_delta | 5–50Δ (asymmetric allowed; free-delta family only) | 10–25Δ |
| long_put_expiry | +7d … +90d beyond front | +14…+35d |
| long_call_expiry | same, may differ from put side | +14…+35d |
| long_strike_offset | same-strike (calendar) … ±100 pts (diagonal) | 0–50 pts wider |
| net_position | credit required? min credit as % of R | yes; ≥ 10% |

### 8.2 Entry (resting EV-gated orders)
| Param | Range | Notes |
|---|---|---|
| credit_threshold | 20–60% of reference width | his quotes: 30% typical, 50% "only if ATM/ITM" |
| threshold_reference | short-strike distance / scenario-R / max-gain | definition itself is a sweep dim |
| order_window | Fri open→close; or Thu 2pm→Fri close | when resting orders are live |
| ladder | 1–3 child orders at rising thresholds, sized | his "several orders waiting" |
| no_fill_policy | skip week (default) / relax at 3:30pm Fri by x% | |

### 8.3 Regime module (21-EMA weekly; replicate on 26y candles first)
- ema_len: {13, 21, 34} (21 prior), applied to weekly closes; also test weekly-of-daily consistency.
- State: bull (close > EMA), bear (<). Hysteresis band h ∈ {0, 0.25, 0.5}·ATR(weekly) to define "rejection"/"retracement":
  - **crossover:** state flip on weekly close.
  - **rejection:** intraweek touch of EMA±h that closes back on the prior side.
  - **retracement:** in bull state, pullback into EMA±h that holds ≥1 close (his "highest-EV" event).
- Action mapping (sweep): {trade only in bull; tilt deltas by state (e.g., bear ⇒ wider put wing / skip / invert); trade all events vs. retracement-only weeks}.
- **Deliverable (expanded 2026-08-10 — the candle study is now confirmed to be his ENTIRE backtest; replicate it end-to-end on real candles):** `reports/candle_study.md`, a data-replication study of the OP's research process (candles-only; makes NO claims about the options strategy):
  - (a) conditional weekly-return distributions above/below the 21-week EMA;
  - (b) the implied coverage bands and their strike distances (feeds the §8.1 percentile family);
  - (c) **inverse solve on his claims:** for each coverage q ∈ [0.80, 0.95], compute the credit (as % of risk) and win/loss profile REQUIRED to reproduce Kelly ~60%, win ~+30% of risk, and EV ~+$450/contract, and state whether the required credits are plausible — final verification of actual credits waits for Pass 2 options data;
  - (d) verify or refute "3 consecutive bad weeks happen below the EMA";
  - (e) using daily highs/lows, tabulate the historical weeks in which the index would have TOUCHED each candidate band edge intraweek — the defense-activation calendar.

  Report contains aggregate statistics, tables, and figures only — no reproducible raw data rows. Data: free daily sources under `data/raw/free/` (gitignored), sources labeled in the report.

### 8.4 Defense policy (the claimed edge; least identified — model as policy space)
- **trigger:** {index touches short strike (intraday), index closes beyond short strike, short-leg delta > d ∈ [0.4, 0.6], position P&L < −y·R, y ∈ [0.3, 1.0]}
- **timing:** {immediate (next bar), EOD of touch day, T−1 only (his stated prior), hybrid: monitor from touch but act T−1}
- **action:** {do nothing (control), close tested side, roll tested short out 1wk, roll out+away to Δ target, convert tested side to vertical, buy back short only (go long-wing), close entire position, add index/ES delta hedge}
- **untested-side rule:** {hold, harvest at ≥80% of max, roll toward}
Encode as a small policy DSL/enum grid so ABC can search it. Log defense-activation weeks separately — identification power concentrates there.

### 8.5 Sizing
risk_definition ∈ §7.4; risk_fraction ∈ {0.10, 0.15, 0.20} (0.15 prior); kelly recompute {static, rolling}; NAV base {start-of-week (prior), current}.

---

## 9. Sweep & identification (`options_strategy.sweep`)

### 9.1 Stage 1 — coarse EOD prune (Track A)
Sobol/LHS ≥ 10,000 configs over §8 (defense collapsed to {none, close-side-EOD}) on EOD options 2016→2026-03. Prune: net expectancy ≤ 0 after fees, weekly WR < 0.75 or > 0.97, weekly-win magnitude outside 15–45% of R, DD profile grossly non-target. Keep top ~5–10% + a random 2% (bias guard). Deliverable: pruning report with parameter marginals.

### 9.2 Stage 2 — intraday simulation (Track B)
Survivors × defense grid (§8.4) × fill models on intraday data. Compute full fingerprint vector per run.

### 9.3 Stage 3 — ABC fingerprint matching (live window 2026-04-01→07-30)
Summary vector S: {ann. Sharpe, ann. Sortino, σ_daily, downside dev, mean daily, %pos days, maxDD, DD-date match (F4 as hard constraint window ±2 days), recovery days, weekly WR, median win %R, VAMI-curve distance (DTW or L2 on log-VAMI)}. Distance ρ = weighted normalized L2 (weights in config; F4 & maxDD heavy). Accept if ρ < ε (ε chosen for ~0.5–1% acceptance). **Posterior = accepted set.** Deliverables: marginal & pairwise posterior plots, cluster description ("the family that matches"), and an **identifiability statement** — expected outcome is a plateau, esp. over defense params. The live curve is treated as pure weekly-diagonal; minor unrelated account activity, if any, is absorbed by the acceptance tolerance ε — do not build machinery for it. Report which fingerprints bind and which don't.

### 9.4 Guardrails against self-deception
- Optuna/TPE may refine within accepted regions but final claims cite region statistics, never a single argmax.
- Every evaluated config goes in the ledger; the trial count feeds DSR (§10).
- No peeking at the live window during Stage 1/2 tuning; it is reserved for matching & out-of-sample checks.

---

## 10. Evaluation & robustness (`options_strategy.eval`)

For pruned survivors and posterior configs:

1. **Full-history performance** 2016→2026 (intraday where data allows; EOD extension back to 2005 optional): IBKR-convention tearsheet (§2.1), regime-sliced (bull/bear per §8.3), yearly table, weekly P&L distribution (skew/kurtosis — expect strong negative skew; report it, don't hide it).
2. **Walk-forward:** anchored + rolling (train 3y / test 6m, step 3m). Parameter-stability heatmaps across folds; a config family only "passes" if the region (not a point) stays profitable OOS.
3. **Deflated Sharpe Ratio** (Bailey & López de Prado) using ledger trial counts; **PBO via CSCV** (16 blocks) over the sweep. These two numbers must appear on the front page of the final report.
4. **Stress book:** named windows — Sep–Nov 2008 (EOD proxy), May 2010, Aug 2011, Aug 2015, Feb 2018, Dec 2018, Feb–Mar 2020, 2022 H1 grind, 2024-08-05, plus **synthetic weekend-gap injector**: perturb Monday opens by −3/−5/−8% with vol +10/+20/+40 pts on live-like configs; and 3-consecutive-bad-week scripts (his nightmare scenario). Report NAV impact distribution and margin feasibility.
5. **Risk-of-ruin:** bootstrap + block-bootstrap weekly P&L (and model-based with fat tails) at 15% deployment; P(NAV < 50%), P(< 30%) over 1y/3y horizons. This directly addresses the "your risk is diabolical" thread critique.
6. **Cost sensitivity:** slippage ×1..×5, fees ×1..×3, fill model CONSERVATIVE vs MID — edge-decay curves.
7. **Capacity note:** displayed-size participation flags aggregated ⇒ rough AUM ceiling estimate.

**Final report must answer:** (a) does the family have positive net expectancy and in which regimes; (b) which parameter regions match his fingerprints and how identifiable are they; (c) do matching regions survive WFO/DSR/PBO/stress; (d) what is the tail/ruin profile at his sizing; (e) what cost/fill assumptions the conclusion is sensitive to.

---

## 11. Validation harness & invariants (continuous, not a phase)

Hard invariants (pytest, run in CI on every commit):
1. **Conservation:** cash + Σ position MTM = NAV at every mark; final NAV = initial + Σ realized P&L − Σ fees.
2. **No-lookahead:** strategies see only `MarketView(t)`. Property test: mutate all data strictly after t ⇒ decisions at t bit-identical. Grep-lint: strategy modules import no raw loaders.
3. **Parity/QA gate:** engine refuses datasets failing §4.2 beyond thresholds.
4. **Settlement:** hand-computed golden cases (ITM/OTM, PM & AM, holiday-shifted) match to the cent.
5. **P&L attribution:** daily Taylor (Δ,Γ,Θ,vega) explains actual P&L within tolerance on non-gap days; residuals reported on gap days.
6. **Golden strategies:** (a) buy-and-hold synthetic index ⇒ NAV = index total return exactly; (b) single short put held to expiry ⇒ P&L = credit − settlement intrinsic − fees exactly; (c) Track A ≡ Track B on EOD-expressible configs (≤1e-6).
7. **Determinism:** same config+seed+data_version ⇒ identical ledger row hash.
8. **Metrics goldens:** §2.1 reconstruction test (2.99/4.45 at rf 2.62%).

---

## 12. Delivery phases & acceptance criteria

### §12.0 Autonomous loop protocol
Phases execute strictly in order but with **no human gate between them**. For the current phase, iterate:
1. **ENGINEER** — re-read this phase's spec + the PLAN sections it references; design; implement or modify code.
2. **GENERATE** — produce the phase's artifacts (code, synthetic worlds, QA reports, sweep runs, matching reports).
3. **VALIDATE** — run this phase's acceptance criteria + all §11 invariants (+ `options_strategy qa` wherever data is touched).
4. **TEST** — full `pytest` + `ruff`; green required.

**Exit check:** every AC machine-verifiably green, with evidence (test IDs, ledger rows, report paths) recorded in `PROGRESS.md` ⇒ commit, tag `phase/pN-complete`, push, advance to the next phase. Any failure ⇒ diagnose and return to ENGINEER.

**Guards:** never weaken a test, tolerance, or AC to advance; never mark an AC complete without artifacts; **stall rule** — 5 consecutive iterations failing the same criterion without measurable progress ⇒ stop, write `STALL_REPORT.md` (what failed, attempts, hypotheses, what's needed), await the user. Commit at every green TEST beat; push at least at phase boundaries.

**Pass structure:**
- **Pass 1 (now):** P0 → P6 entirely on synthetic data — a full-system dress rehearsal. The Pass-1 final report is titled `FINAL_REPORT_SYNTHETIC.md`, labeled SYNTHETIC throughout, and draws **no real-market conclusions**. On completion, stop and tell the user exactly what data to purchase (§4.3).
- **Pass 2 (when purchased data lands in `data/raw/`):** build the actual vendor adapter (P1 addendum), run `options_strategy qa`, bump `data_version`, rerun P2 invariants, then rerun P4 → P6 on real data to produce the true final report.

**Pass rules clarification (2026-08-10, user-approved):**
- The expanded §8.3 candle study runs immediately, on REAL free daily data (`data/raw/free/`). It is a **data-replication study of the OP's research process, not a strategy simulation**, so it is an explicit user-approved exception to Pass 1's synthetic-only rule, and its conclusions ARE real-market conclusions about his methodology. It is labeled candles-only and makes no claims about the options strategy.
- Free data under `data/raw/free/` (gitignored like everything under `data/`) does NOT trigger Pass 2. **Pass 2 triggers only when purchased intraday OPTIONS data lands in `data/raw/`.**
- The strategy-simulation phases remain synthetic until Pass 2, unchanged. P4+ re-runs with the §8.1 percentile-band family are SYNTHETIC re-runs (Pass-1 machinery validation with the new family), tagged distinctly; the real-data runs happen in Pass 2 as always.

**P0 — Bootstrap, scaffold + synthetic world.** Git bootstrap: `git init -b main` in the project folder (it is NOT yet a git repo), create `.gitignore` (Python caches, `.venv/`, `data/raw/`, `data/vendor/`, scratch outputs) and a minimal `README.md` (points to CLAUDE.md/PLAN.md, research-only disclaimer), initial commit under the user's git identity, create GitHub remote and push (`gh repo create options_strategy --public --source=. --push` via the user's authenticated `gh`), GitHub Actions CI (ruff + full pytest) on `main`. Then repo per §3.1, conda env (`options_strategy`, python 3.12; user directive 2026-08-06), config system, ledger, synthetic generator (§5). ✅ AC: repo on GitHub with Actions green; `options_strategy qa` clean on synthetic; deterministic regeneration.

**P1 — Pricing & data layer.** Schemas, one vendor adapter stub + synthetic adapter, QA gate, forwards via parity, IV/greeks, settlement. ✅ AC: IV round-trip ≤1e-6; parity forwards ≈ generator truth; settlement goldens pass.

**P2 — Engine core.** Events, portfolio, fees (≈$1.60/leg default), margin/scenario-R sizing, fills incl. resting combo models, EOD marking. ✅ AC: invariants 1,4,5,6a,6b,7 pass; fee unit test reproduces author's numbers.

**P3 — Strategy family + regime.** Diagonal builder over §8.1–8.2, EMA regime module + **26y candle regime study deliverable**, defense policy DSL (§8.4), Track A compilation. ✅ AC: a fully hand-specified example week reproduces hand-calculated P&L; regime events match a reference implementation on scripted synthetic; Track A≡B test passes.

**P4 — Coarse sweep (Track A).** §9.1 at ≥10k configs — Pass 1 on synthetic EOD data; Pass 2 rerun on real EOD data. ✅ AC: pruning report with marginals; runtime budget: ≤ ~2 s/config/decade EOD on a laptop (soft; profile before optimizing).

**P5 — Intraday sim + defense.** §9.2 — Pass 1 on synthetic intraday worlds (incl. scripted crash/gap scenarios); Pass 2 rerun on real intraday data. All defense variants covered by scenario tests (incl. a scripted weekend-gap week exercising F4-style losses). ✅ AC: fill-model bounds reported side-by-side; defense-week logs emitted.

**P6 — ABC matching + robustness + final report.** §9.3 + §10 in full. Pass 1: run the full pipeline against a **synthetic "mystery trader"** — a hidden config generating a fake live curve — and verify the ABC machinery recovers its parameter region (end-to-end identification test); output `FINAL_REPORT_SYNTHETIC.md`. Pass 2: run against the real fingerprints (§2) for the true final report. ✅ AC: posterior report with identifiability statement; DSR & PBO on front page; stress book; risk-of-ruin; report answers §10(a–e); Pass 1 additionally requires the mystery-trader region to be recovered.

**P7 (optional) — capacity deep-dive.**

---

## 13. Working agreements for Claude Code

- Log every nontrivial modeling choice in **ASSUMPTIONS.md** (one line: date, choice, alternative, why).
- Never change metric definitions, fingerprint targets, or acceptance criteria silently — if one seems wrong, stall-stop and write it up in `STALL_REPORT.md` rather than editing it.
- Experiments run from configs, never edited constants; if it isn't in the ledger, it didn't happen.
- No fabricated or downloaded-from-memory market data. Synthetic is labeled synthetic everywhere, including plots.
- Prefer boring code: explicit loops over clever broadcasting where clarity wins; numba only after a profile shows need.
- When real data arrives: run `options_strategy qa` first, commit the QA report, bump `data_version`, then rerun P2 invariants before any strategy runs.
- **Autonomous defaults** (do NOT block the loop on questions; pre-seed these in ASSUMPTIONS.md and surface them in every report): Pass 1 = synthetic data only; account size **$100,000** for fee granularity; rf = synthetic rates curve in Pass 1 / 3M T-bill in Pass 2; vendor adapter built only when real data actually arrives (formats in §4). Stall-stop and ask the user only for genuine external blockers (missing data, unauthenticated `gh`, scope conflicts).

## 14. SPX-specific pitfalls checklist (encode as tests where possible)

- SPXW = PM-settled (4pm close print); SPX monthlies = AM-settled (SET, Friday open) — mixing these silently corrupts expiry P&L.
- Holiday-shifted expirations (Good Friday etc.); early-close days (day after Thanksgiving, Christmas Eve) change the defense clock.
- Expiry availability by era: M/W/F weeklies historically, Tue/Thu added ~mid-2022 ⇒ never let a 2018 backtest trade a Tuesday expiry.
- Index quotes ≠ tradeable: SPX index level is not an order book; touch-defense triggers on the index must be honest about option-side execution costs.
- Wide wings after vol spikes: NBBO width explodes; CONSERVATIVE fill model + quality flags must gate defense fills, else the backtest "defends" at fantasy prices.
- Overnight/weekend gaps dominate this structure's tail (F4 is the live proof). Any result without gap stress is incomplete.
- rf ≠ 0 in 2026 (§2.1); metrics without excess returns won't match IBKR.
- OI/volume are EOD fields — don't use them intraday for t-visible decisions.

## 15. Guardrails

Research software only. No order-routing hooks, no broker credentials, no live-trading pathway. Reports must carry deflated metrics (DSR/PBO) alongside raw ones, and a plain-language caveat that a matched configuration is not evidence of the original trader's true rules nor of future profitability. Nothing produced here is investment advice.

**Public-repo data rule:** the repository is public. Purchased/licensed market data (CBOE, Theta Data, Polygon, IBKR exports, etc.) must never be committed — that is public redistribution and a license violation. `data/raw/` and `data/vendor/` stay gitignored permanently; derived aggregates in committed reports must be transformative summaries (metrics, plots), never reconstructable quote/trade records. If licensed data is ever found in git history, treat it as a stall-stop: halt pushes, report to the user, and require a history rewrite before resuming.

---
*End of handoff. Start with Phase 0.*
