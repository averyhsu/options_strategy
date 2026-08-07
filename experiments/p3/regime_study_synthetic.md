# Regime study — SYNTHETIC world

**SYNTHETIC DATA.** This study runs the 21-EMA weekly regime machinery on a
scripted synthetic world to validate the pipeline (PLAN §8.3). It supports
no real-market conclusion; the 1999->present replication happens in Pass 2.

- world: `regime-26y-synthetic` (data_version `synthetic-50300bded804`)
- weeks analyzed: 1335 | ema_len 21

## Weekly returns by regime state

| state | n | mean ret | win rate | worst |
|---|---|---|---|---|
| bear | 501 | -0.9204% | 41.7% | -13.24% |
| bull | 834 | 0.5986% | 70.9% | -5.37% |

## Events

| event | n | mean next-week ret |
|---|---|---|
| crossover | 120 | -0.2175% |
| none | 1106 | 0.0566% |
| rejection | 50 | -0.2592% |
| retracement | 59 | 0.2765% |

## Losing-week clusters (the author's claim, synthetic rehearsal)

- streaks >= 2: 130; streaks >= 3: 58
- of the >=3 streaks, started while state was BEAR: 18, BULL: 40
