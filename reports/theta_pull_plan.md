# ThetaData paid-month pull plan (Options STANDARD, $80/mo)

Request inventory for the one paid month that acquires everything Pass 2
needs beyond the free-tier preview. STANDARD: tick-level options history
from 2016-01-01, 4 concurrent requests. All output is licensed vendor data
→ `data/raw/theta/` (gitignored, never committed).

**Calibration caveat:** contract counts marked (†) are estimated from CBOE
listing rules (M/W/F SPXW weeklies + SPX monthlies ≤ 63 DTE ≈ 28–30
expiries per sample date; 5-pt strike spacing near ATM widening to 25/50 in
the wings). The free-tier preview pull measures real contracts-per-day —
re-run these numbers from `raw_manifest.json` before the paid month starts.
Request timing assumes ~0.4–1 s/request sustained on 4 lanes.

## (a) Four remaining kill windows — EOD-basis credit-check slice

28 sample dates (calm-2017 ×6, volmageddon-feb-2018 ×5, covid-mar-2020 ×7,
bear-2022 ×10) from the mini-purchase spec in `reports/candle_study.md`,
via the existing `at_time` slice fetcher (3 snapshots: 10:00 / 15:45 /
16:00 ET).

| quantity | formula | value |
|---|---|---|
| requests | 28 dates × 2 roots × ~15 expiries†/root × 3 times + listings | **~2,500** |
| wall time | 2,500 ÷ 4 lanes × ~0.7 s | **~7–15 min** |
| rows kept | ~1,500 quote rows/date-snapshot × 84 date-snapshots | ~130k |
| disk | parquet, ~40 B/row | **< 10 MB** |

## (b) 2016 → present decade, 1-minute NBBO bars (filtered)

Filters: DTE ≤ 63 (server-side), strikes within ±15% of spot, RTH only.
This is the dominant item and the reason to sanity-check scale first:

| quantity | formula | value |
|---|---|---|
| trading days | 2016-01-04 → present | ~2,670 |
| contracts/day | ~30 expiries† × ~120 strikes† × 2 rights, post-filter | ~5,000–9,000 |
| rows/day @ 1-min | contracts × 390 bars | ~2.0–3.5 M |
| rows total | days × rows/day | **~5–9 BILLION** |
| disk | ~25–40 B/row parquet | **~150–350 GB** |
| requests | per (root, expiry, month) bulk ≈ 2,670 days ÷ 21 × 30 | ~65–85k |
| wall time | 75k ÷ 4 lanes × ~1 s | **~5–6 h** (transfer-bound; could be 2–3×) |

**Recommendation before committing disk:** the strategy needs 1-min density
only around entries and defense triggers. A 15-min bar decade is ~25–45 GB
and preserves the touch/defense timeline; 1-min (or tick, item c) can then
be pulled surgically. Decide before the paid month; both variants fit the
same request structure, only `ivl` changes.

## (c) Tick NBBO — defense-calendar touch weeks only

Candle-study §(e), q=0.90 touch weeks restricted to 2016+ (STANDARD floor):
put-side 81 + call-side 65 entry-week touches, ≤ **~146 weeks** (unique
weeks fewer; exact list generated from the study artifact at pull time).
Scope: the traded legs only (2 shorts + 2 wings + roll candidates ≈ 8–12
contracts/week), entry Friday + 5 defense days.

| quantity | formula | value |
|---|---|---|
| requests | 146 weeks × ~10 contracts × 6 days | ~9k |
| rows | ~100–400k NBBO ticks/contract-day × 8,760 contract-days | **~1–3.5 B ticks** |
| disk | ~30 B/row | **~30–100 GB** |
| wall time | 9k ÷ 4 lanes × ~3–10 s (tick payloads are heavy) | **~2–7 h** |

Trim lever if needed: 100 ms conflation or quote-change-only dedup cuts
~5–10× with no loss for defense-trigger timing.

## (d) Index history 2022+ (optional validation)

SPX 1-min index prints 2022-01-01 → present: ~1,160 days × 390 bars ≈
450k rows, < 50 MB, ~60 requests, minutes. **Caveat: this needs Theta's
INDEX subscription (separate product; STANDARD index tier), which the data
plan currently excludes** — it is optional validation of the parity-derived
index only. Pre-2022 stays parity-derived regardless (wider touch-timing
error bars, logged in ASSUMPTIONS.md 2026-08-17).

## Sequencing for the paid month

1. Day 1: probe + (a) — minutes; unblocks the 6-regime credit check.
2. Day 1–2: (c) touch-week ticks — bounded, high value for defense modeling.
3. Rest of month: (b) after the density decision, chunked + resumable;
   re-verify disk headroom after the first week's chunks.
4. (d) only if the index add-on is approved.

Every dataset lands behind `options_strategy qa` + a `data_version` bump
before any strategy run touches it (CLAUDE.md non-negotiables).
