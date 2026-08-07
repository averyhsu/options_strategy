# ASSUMPTIONS.md — modeling & process assumptions log
One line each: `YYYY-MM-DD | choice | alternative considered | why`. Append-only.

2026-08-06 | Autonomous loop mode: phases advance on green AC without human gates (PLAN §12.0) | phase-gated human review | user directive; stall rule + no-weakening guard compensate
2026-08-06 | Pass 1 runs P0–P6 entirely on synthetic data | wait for purchased data | data not yet purchased; full-system dress rehearsal de-risks Pass 2
2026-08-06 | Account size default $100,000 (fee granularity, contract rounding) | ask user | avoid blocking the loop; surfaced in every report
2026-08-06 | rf = synthetic rates curve (Pass 1); 3M T-bill (Pass 2) | SOFR curve | matches PLAN §2.1 implied rf ≈ 2.6% check
2026-08-06 | Vendor adapter built only when real data lands in data/raw/ | build speculative Theta/CBOE adapters now | avoid coding against guessed schemas
2026-08-06 | miniconda env `options_strategy` (py3.12) + pip, not uv | uv per PLAN §3.2 | user directive at kickoff
2026-08-06 | Sessions/holidays from exchange_calendars XNYS as CBOE proxy | XCBOE calendar | exchange_calendars ships no CBOE index-options calendar (only XCBF futures); SPX trading days follow the NYSE holiday schedule
2026-08-06 | 1-min bar timestamps label the bar START (ET, tz-aware); daily NAV marks use the close of the last RTH bar | bar-end labels | vendor-common convention; documented so real-data adapters normalize to it
2026-08-06 | Holiday shift: Friday expiries -> preceding session, Mon-Thu weeklies -> following session, collisions dedupe | shift everything backward | CBOE convention (Good Friday -> Thu; MLK Mon -> Tue; Thanksgiving Thu merges into Fri); encoded in tests/unit/test_calendar.py
2026-08-07 | Synthetic surface: SSVI (Gatheral-Jacquier) on Heston expected integrated variance, butterfly conditions asserted at worldgen | Heston characteristic function pricing | PLAN §5 blesses the simpler surface path; closed-form no-arb checks
2026-08-07 | QA stale detector: unchanged bid+ask >= 45 min AND mid >= $0.50 | flag all frozen runs | deep-wing quotes are legitimately static; sub-$0.50 freezes carry no signal (vendor-style heuristic)
2026-08-07 | QA DF-vs-truth gate restricted to parity fits with tenor >= 1 day (forwards gated at ALL tenors, DF still reported ungated as info) | flat DF tolerance at all tenors | parity slope cannot resolve DF minutes before settlement (1 - r*tau ~ 1e-6); first empirical run showed 1.3e-3 slope noise there vs 5e-6 forward error
