# proving-ground leaderboard

Metric: kernel-verified partial credit = discharged subgoal weight / total weight (0 = none, 1.0 = a complete kernel-checked proof). Reported per tier — never blended. The open tier reports solved/reductions only, not a partial scalar (see the open-tier note for why).

## 🏆 Open-tier results

**Genuinely open conjectures.** No partial scalar — solving one is binary and would be historic. What's reported is verified reductions and the new, smaller open lemmas they surface (which re-enter the corpus). ⭐ marks an actual solve:

- **claude-code/opus** — 2 verified reduction(s), 2 new open lemma(s) surfaced
- **claude-code/sonnet** — 2 verified reduction(s), 2 new open lemma(s) surfaced
- **claude-code/haiku** — 1 verified reduction(s), 2 new open lemma(s) surfaced

## Tier: `solved_recent`

_Calibration / contamination canary. A model that fails here is broken, not challenged._

| Rank | Model | Attempted | Solved | Partial | Mean | Best |
|---:|---|---:|---:|---:|---:|---:|
| 1 | claude-code/opus | 2 | 2 | 0 | 1.000 | 1.000 |
| 2 | claude-code/sonnet | 2 | 2 | 0 | 1.000 | 1.000 |
| 3 | claude-code/haiku | 2 | 1 | 0 | 0.500 | 1.000 |

## Tier: `weakly_open`

_Open to current provers but plausibly tractable. Moving the needle here is doing something real._

| Rank | Model | Attempted | Solved | Partial | Mean | Best |
|---:|---|---:|---:|---:|---:|---:|
| 1 | claude-code/haiku | 3 | 3 | 0 | 1.000 | 1.000 |
| 2 | claude-code/sonnet | 3 | 3 | 0 | 1.000 | 1.000 |
| 3 | claude-code/opus | 3 | 2 | 0 | 0.667 | 1.000 |

## Tier: `open`

_Genuinely open conjectures. No partial scalar is reported here — partial progress on an unsolved problem is not a real, ungameable quantity. We report solved (binary) and verified reductions that surface new open lemmas. Solving one is a contribution to mathematics._

| Rank | Model | Attempted | Solved | Verified reductions | Open lemmas surfaced |
|---:|---|---:|---:|---:|---:|
| 1 | claude-code/opus | 2 | 0 | 2 | 2 |
| 2 | claude-code/sonnet | 2 | 0 | 2 | 2 |
| 3 | claude-code/haiku | 2 | 0 | 1 | 2 |

