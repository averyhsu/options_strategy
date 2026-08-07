# ASSUMPTIONS.md — modeling & process assumptions log
One line each: `YYYY-MM-DD | choice | alternative considered | why`. Append-only.

2026-08-06 | Autonomous loop mode: phases advance on green AC without human gates (PLAN §12.0) | phase-gated human review | user directive; stall rule + no-weakening guard compensate
2026-08-06 | Pass 1 runs P0–P6 entirely on synthetic data | wait for purchased data | data not yet purchased; full-system dress rehearsal de-risks Pass 2
2026-08-06 | Account size default $100,000 (fee granularity, contract rounding) | ask user | avoid blocking the loop; surfaced in every report
2026-08-06 | rf = synthetic rates curve (Pass 1); 3M T-bill (Pass 2) | SOFR curve | matches PLAN §2.1 implied rf ≈ 2.6% check
2026-08-06 | Vendor adapter built only when real data lands in data/raw/ | build speculative Theta/CBOE adapters now | avoid coding against guessed schemas
2026-08-06 | miniconda env `options_strategy` (py3.12) + pip, not uv | uv per PLAN §3.2 | user directive at kickoff
