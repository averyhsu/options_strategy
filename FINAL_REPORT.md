# FINAL REPORT — Pass 2 (REAL DATA)

**Weekly SPX double-diagonal family: identification, expectancy, and robustness
on real market data (2016-01-04 → 2026-08-10).**
Research software only — no live trading, no order routing. Not investment advice.

Data: ThetaData 15-minute NBBO (STANDARD, one paid month, `DOWNLOADS_COMPLETE`
2026-08-23 with per-file checksums), 15:45 ET decision basis, parity-derived
spot/settlements (no index subscription), QA'd under the versioned real-NBBO
config; every run in `experiments/ledger.parquet`. Worlds:
`theta_decade_world_v2` (2,665 sessions), `theta_live_world_v1` (547 sessions),
`theta_slice_v1` (51 spec dates × 3 snapshots), `theta_eod_preview_v1`.

---

## Headline answers (PLAN §10 a–e)

**(a) Does the family have positive net expectancy, and in which regimes?**
Mostly no; narrowly and regime-dependently yes. Across 16,384 space-v4
configs on the real decade, 7,630 traded at all; among actives the median
weekly WR is 48% and the median raw Sharpe 0.10 — flat. **Exactly one config
in 16,384 satisfies the author-profile pruning bands** (WR 75–97%, win
magnitude 15–45% of R): a selective `retracement_only`, delta-family,
near-wing, no-defense config — WR 81%, median win 19% of R, raw Sharpe 0.79,
maxDD 12.4%, 79 cycles/decade. Regime texture (stress windows, top-5 kept
configs): COVID-Mar-2020 was a **+40% median gain** (the long-vega near-calendar
wings win in crashes), while Volmageddon-Feb-2018 was **−32% median / −76%
worst** — the family's true kill window is the vol event *without* a large
spot crash. Bear-2022 −7%, Dec-2018 −6%, Aug-2024 and the 2026 live window
roughly flat-positive.

**(b) Which parameter regions match the author's fingerprints, and how
identifiable are they?** **None.** The ABC match over the real 2026 live
window (16,384 candidates, F1–F14 targets, F4 drawdown-date hard gate ±2d)
accepts **zero** candidates (`reports/fingerprint_match.md`). This zero
survived three rounds of machinery falsification (sizing floor, front-expiry
selection, 16:00 quote degradation — each found, fixed, and rerun; the final
sweep demonstrably trades 17/17 live Fridays). The active family loses over
the live window (median Sharpe −1.43, WR 43%) while the published record
shows +2.99 / ~88%. The nearest soft-ranked candidates DO resemble the
record's scalar stats (Sharpe 2.9–3.9, WR 71–86%, maxDD 8–9%) — but only at
sparse cadence (≤7 of 17 weeks) and with drawdowns on May 15/Jun 2, never
the record's Jul 10→13 weekend. Model gaps that could account for the
mismatch without impugning the record: the collapsed defense proxy vs richer
rolling, EOD-mid vs resting intraday credit fills, non-diagonal account
activity beyond the tolerance. On the evidence: the published curve is not
reproducible within this family as modeled.

**(c) Do matching regions survive WFO/DSR/PBO/stress?** There are no
matching regions (b); for the 316 kept configs generally: **DSR = 0.23**
(the best decade Sharpe of 0.96, deflated for 16,384 trials, has ~23%
probability of genuine skill), **PBO = 0.13**, and anchored walk-forward
shows median OOS share-profitable of 48% with median OOS mean daily return
≈ 0.015 bp — i.e., selection does not transfer out of sample. The single
author-band survivor is one config among 16,384 trials; its deflated
evidence is correspondingly negligible.

**(d) Tail/ruin profile at the author's sizing (R = 10–20% NAV weekly).**
Block-bootstrap over 16,665 kept-config weekly outcomes: **P(NAV < 50% of
start) ≈ 15% within 1 year and 44% within 3 years**; P(NAV < 30%) ≈ 4% (1y)
/ 21% (3y). The −76% worst Volmageddon impact shows the mechanism. At this
sizing the family is ruin-prone regardless of average expectancy.

**(e) Cost/fill sensitivity.** Fees: robust — tripling per-leg fees moves
median kept-config expectancy by <2% (debit structures; fees are small
relative to premium). Fills: the CONSERVATIVE and MID fill models produced
identical results under `eod_immediate` entries — the fill-model spread never
bound, so **execution-price sensitivity is NOT measured by this pass** and
the resting-order fill question (the author's stated mechanism) remains open.
The `delta_hedge` defense variant is numerically unstable on real data
(unbounded hedge accumulation, NAV → −$1.28M in one grid cell) and its rows
should be treated as invalid rather than evidence.

---

## The credit-check verdict (six regimes, real chains)

The author's "+30% of risk" claim under the **credit reading is refuted**:
1.7% of 1,836 structures priced as net credits at 15:45 ET across all six
regime windows — and that pocket sits exactly where he said it would
(calm-2017, ATM shorts, widest wings). Under the **return-on-risk reading**
the claim is achievable predominantly with 14-day fronts at q90–q95 or
near-ATM shorts (100% of entry dates in all four kill-window regimes have
at least one corner structure reaching +30%R). `reports/credit_check.md`.

## Identification summary

The published record is **not identifiable within this family**: zero ABC
acceptance; the only author-band survivor on the decade is a low-cadence
selective config whose win magnitude (19% of R) undershoots the claimed 30%.
What the data does support: the *structural* reading of the author's
disclosures (debit near-calendars, 14d fronts, selective entries, ATM-ish
credit pockets in calm tape) is consistent with real chains; the published
*performance curve* is not reproduced by any parameterization of that
structure under this pass's execution model.

## Caveats & provenance

- One named data gap (vendor-broken 2021-06-21 contract-day tick file);
  everything else verified via `experiments/theta_downloads/MANIFEST.md`.
- QA verdicts on all real worlds are NOT CLEAN under full strictness by
  design (0.06–0.16% flagged rows, excluded from fills; parity tolerance
  real-NBBO tier documented in ASSUMPTIONS.md 2026-08-18).
- Spot & settlements are parity-derived (no index subscription); PM settle
  proxy = 15:45 parity spot.
- All modeling choices and mid-pass corrections (including three machinery
  misdiagnoses and their fixes) are logged in ASSUMPTIONS.md with dates.

*Generated 2026-08-24. Pass-2 artifacts: experiments/p4_pass2, p5_pass2,
p2_match, p6_pass2, theta_* QA evidence; reports/credit_check.md,
fingerprint_match.md, theta_pull_plan.md.*
