# ThetaData paid-month pull plan (Options STANDARD, $80/mo)

Request inventory for the one paid month that acquires everything Pass 2
needs beyond the free-tier preview. STANDARD: tick-level options history
from 2016-01-01, 4 concurrent requests. All output is licensed vendor data
→ `data/raw/theta/` (gitignored, never committed).

**RECALIBRATED 2026-08-18** from the preview pull's `raw_manifest.json`
(104 real sessions): median **15,663** contract-rows/day raw (both roots,
DTE ≤ 63, all strikes), **~11.8k/day** after the ±15% strike trim —
2024–2026 tape; 2016–2017 lists fewer weeklies so early years run lighter.
Paid-month amendments (user, 2026-08-18): decade density = **15-minute
bars** (1-min rejected); touch weeks = **union of q85–q95**; index add-on
**permanently excluded**. STANDARD verified active (auth handshake
options=2; 2017 at_time probe returned rows).

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

## (b) 2016 → present decade, 15-MINUTE NBBO bars (DECIDED 2026-08-18)

Filters: DTE ≤ 63 (server-side), strikes within ±15% of spot, RTH only.
1-minute rejected: preview measured ~11.8k filtered contracts/day, and
1-min buys resolution the strategy never uses — defense timing is covered
by the tick layer (c).

| quantity | formula | value |
|---|---|---|
| trading days | 2016-01-04 → present | ~2,670 |
| contracts/day | measured 11.8k (2024–26); early years lighter | ~5,000–12,000 |
| rows/day @ 15-min | contracts × 26 RTH bars | ~130–310k |
| rows total | days × rows/day | **~500–800 M** |
| disk | ~30–40 B/row parquet | **~25–40 GB** |
| requests | per (root, session) with expiration=* | ~5,340 |
| wall time | sequential at ~1–3 s/request (payload-bound) | **~2–5 h** |

## (c) Tick NBBO — defense-calendar touch weeks (AMENDED: q85–q95 union)

Candle-study §(e) touch weeks restricted to 2016+ (STANDARD floor), now the
**union of q85, q90, q95 put/call touches** (user amendment 2026-08-18) —
roughly 1.5–2× the q90-only list, so ≈ **200–290 weeks** (exact list
generated from the study machinery at pull time). Scope: the traded legs
only (2 shorts + 2 wings + roll candidates ≈ 8–12 contracts/week), entry
Friday + 5 defense days. Quote-change-only dedup applies if projected disk
exceeds ~100 GB.

| quantity | formula | value |
|---|---|---|
| requests | 146 weeks × ~10 contracts × 6 days | ~9k |
| rows | ~100–400k NBBO ticks/contract-day × 8,760 contract-days | **~1–3.5 B ticks** |
| disk | ~30 B/row | **~30–100 GB** |
| wall time | 9k ÷ 4 lanes × ~3–10 s (tick payloads are heavy) | **~2–7 h** |

Trim lever if needed: 100 ms conflation or quote-change-only dedup cuts
~5–10× with no loss for defense-trigger timing.

## (d) Index history — EXCLUDED PERMANENTLY (user amendment 2026-08-18)

No Theta index subscription, ever, under this plan. Pre- AND post-2022
intraday index levels stay parity-derived from option quotes (free ^GSPC
candles for daily context); touch-timing error-bar caveat stands
(ASSUMPTIONS.md 2026-08-17).

## Sequencing for the paid month

1. Day 1: probe + (a) — minutes; unblocks the 6-regime credit check.
2. Day 1–2: (c) touch-week ticks — bounded, high value for defense modeling.
3. Rest of month: (b) after the density decision, chunked + resumable;
   re-verify disk headroom after the first week's chunks.
4. (d) only if the index add-on is approved.

Every dataset lands behind `options_strategy qa` + a `data_version` bump
before any strategy run touches it (CLAUDE.md non-negotiables).
