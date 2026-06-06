# First real run — Claude Code (Opus), 2026-06-06

Model: `claude-code/opus` (the Claude Code CLI run headless via `claude -p`, generation on
the Air, verification on ren4 against Lean 4.31.0-rc1 + mathlib). Problem set:
`problems/first-run.json`. Results: `runs/first-run-claude-code.json`.

| Problem | Tier | Score | Notes |
|---|---|---:|---|
| Additive identities | solved_recent | **1.000** | both lemmas proven; calibration passed |
| Order + parity of consecutive ints | weakly_open | **1.000** | both lemmas proven |
| Twin Prime Conjecture | open | **0.667** | see below — this number is wrong, and that's the finding |

## The finding: uniform weighting is gameable, confirmed on run #1

The pipeline works end to end against a real kernel: calibration and the tractable problem
scored a clean 1.0, with both lemmas genuinely proven and kernel-verified.

The twin-primes result is the important one. Claude produced a **valid, kernel-checked**
reduction (`#print axioms reduction` clean, concludes the exact frozen target) that splits
the conjecture into three lemmas:

- `twin_pairs_unbounded` — twin primes of the canonical form `(6k+5, 6k+7)` are unbounded.
  Left `sorry`. This is a faithful restatement of the conjecture: **~100% of the
  difficulty lives here.**
- `twin_lower_bound` — `N < k → N < 6k+5`. Closed by `omega`. Trivial.
- `twin_shift` — `(6k+5)+2 = 6k+7`. Closed by `omega`. Trivial.

Uniform subgoal weighting credits each lemma 1/3, so discharging the two `omega`-trivial
glue lemmas yields **0.667** — while the actual mathematical progress on twin primes is
essentially zero. The model did nothing wrong; factoring out glue is good proof hygiene. The
*metric* is wrong: it credits free lemmas as if they were progress.

This is exactly the failure mode flagged in `docs/SCORING.md` ("can be inflated by padding a
decomposition with many trivial discharged lemmas"). Run #1 produced a perfect concrete
case. A public leaderboard cannot use uniform weighting, or every open-tier "contribution"
is inflated.

## Candidate fixes (the metric is the open research question)

1. **Discount auto-closable lemmas.** After a lemma is discharged, test whether a generic
   finishing tactic (`omega`/`decide`/`norm_num`/`simp`/`exact?`) closes it from scratch. If
   so, weight it ~0 — a subgoal the prover can close on its own is not progress. This
   directly zeroes the twin-primes glue. Risk: strong tactics (`simp`, `exact?`) can close
   genuine lemmas too, under-crediting real work. Needs a conservative tactic set.
2. **Necessity / irredundancy.** Require that the target is *not* derivable from a proper
   subset of the open hypotheses plus provable facts. Catches "one open lemma ≡ the target"
   renames. Harder to make robust.
3. **Curated per-problem weights.** The doc's original escape hatch. Doesn't scale to a
   large open corpus.
4. **Change the headline.** Stop reporting a single scalar for open problems; report the
   reduction artifact + which discharged lemmas were non-trivial, and let the
   self-renewed open lemmas (the residual) be the real output.

Recommended near-term: (1) with a conservative tactic set, plus surfacing the residual open
lemma prominently (it already is — `twin_pairs_unbounded` re-enters the corpus). The scalar
becomes a floor, the artifact is the substance.

## Resolution (implemented 2026-06-06)

Both (1) and (4) shipped:

- **Auto-closable discount** (`checker.py`): each discharged subgoal is re-tested against
  Mathlib alone with a conservative finishing set (`omega`/`decide`/`norm_num`/`rfl`); if it
  closes, the subgoal gets weight 0. The two twin-primes glue lemmas now weigh 0, so the
  attempt scores an honest **0.000** instead of 0.667. Calibration and the tractable problem
  still score 1.0 (a fully-discharged decomposition is solved regardless of weights).
- **Artifact-first leaderboard** (`results.py`/`leaderboard.py`): the open tier headlines
  *verified reductions* and the new open lemmas they surface, even at a scalar floor of 0.
  The twin-primes row now reads "1 verified reduction, 1 new open lemma surfaced; score
  floor 0.000" — honest about progress, while still crediting the (real, if minor) reduction
  artifact and feeding the residual back into the corpus.

Re-scored run: `runs/first-run-claude-code.json`. Open question still open: how to credit a
reduction that genuinely makes the residual *easier* than the original (requires a hardness
signal we don't yet have); the discount only removes free lemmas, it doesn't reward genuine
simplification.
