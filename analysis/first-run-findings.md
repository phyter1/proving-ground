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

## Multi-model run (Opus / Sonnet / Haiku), 2026-06-06

`runs/benchmark-v1-claude.json`, 7 problems (`problems/benchmark-v1.json`), three Claude
models via the Claude Code CLI, verified on ren4. Highlights:

- **The discount is necessary but not sufficient.** Haiku decomposed Goldbach into the open
  core plus four *finite* cases (`∃ p q, prime p ∧ prime q ∧ p + q = 8`, etc.). Those are
  mathematically trivial but **not** auto-closable — `decide` can't discharge an existential
  over ℕ — so each survived the discount as weight 1 and inflated the scalar to **0.8**.
  Meanwhile Opus gave an honest twin-primes decomposition (isolating
  `{p | Prime p ∧ Prime (p+2)}.Infinite` and proving a real unboundedness lemma) and still
  scored **0.5**, because the proved lemma is trivial *relative to* the open core.
- **Conclusion: don't report a partial scalar on the open tier at all.** A partial number on
  a genuinely open problem isn't a real, ungameable quantity. The open tier now reports only
  *solved* (binary) and *verified reductions* + residual open lemmas. This neutralizes the
  Goldbach padding (it's just "1 verified reduction" like everyone) and stops overstating
  honest-but-trivial decompositions. Partial credit remains on `solved_recent` /
  `weakly_open`, where the problems are closed and proving a lemma genuinely is progress.
- **Honest model differentiation appeared:** Haiku flubbed the trivial `add-identities`
  calibration; Opus failed `even-or-odd` by citing a non-existent lemma (`even_zero`) — the
  checker correctly rejected it (not a false negative; the identifier truly is unknown in
  this mathlib). The verifier behaves.

Implemented in `results.py` (`rank_open`, suppressed open scalar) and `leaderboard.py`
(open-tier table = solved + verified reductions + lemmas surfaced; headline ⭐ = an actual
solve). The deeper open question — rewarding genuine *simplification* of the residual —
still needs a hardness signal we don't have.

## Hardness signal: dual failure modes (ren1 fleet, June 2026)

The cross-model Jaccard hardness module shipped in beat 652 (`hardness.py`). Empirical
data from ren1 fleet runs (`fleet-collect-config-ren1.json`) exposed two failure modes:

**Failure mode 1 — calibration false positive (token-Jaccard surface variation).**
`calib-add-identities`: qwen3.5 returns `∀ n : ℕ, n + 0 = n`, gemma4 returns `n + 0 = n`.
These are the same proposition — but raw token-Jaccard scores them as fully disjoint,
producing hardness_score = 1.0 on a trivially solvable calibration problem. The metric
marked "easy" as "maximally hard."

**Failure mode 2 — frontier null collapse.**
`twin-primes` across all tested model families (qwen3.5/Alibaba, gemma4/Google,
granite/IBM): all three models return degenerate or near-degenerate single-subgoal
restatements of the target. N_real < 2 after filtering → hardness = null. The metric
cannot distinguish "this problem is so hard no decomposition strategy is known" from
"these models lack the capability to decompose this problem." Both look like null.

**Root cause of failure mode 1.** Token-Jaccard is blind to universal quantifier
equivalence: `∀ n : ℕ, n + 0 = n` and `n + 0 = n` share almost no tokens despite being
the same mathematical proposition.

**Fix shipped (June 2026, `hardness.py`).** `_normalize_statement()` strips leading `∀`
quantifier prefixes before Jaccard comparison. `compute_consensus` uses normalized sets for
Jaccard; raw sets for `novel_statements` output. `is_degenerate` adds a normalized exact-
match phase between the raw exact match and the raw token containment check. 179 tests
pass. The calibration case now scores hardness ≈ 0.0 correctly; the frontier null pattern
is unaffected (correct behavior — the signal genuinely is undefined when no model can
produce a real decomposition).

**Reframe: decomposability signal, not hardness signal.**
The metric measures *decomposability diversity across models*: whether independent models
find distinct decomposition paths. This is a proxy for hardness only when (a) the models
are capable of decomposing if a strategy exists, and (b) a known decomposition strategy
exists. For genuine research-frontier problems, condition (b) fails — no known strategy
→ all models collapse to restatements → null. The null is correct, not a bug. A null
result for an open conjecture means "no tested model can decompose this problem," which
is information, not measurement failure.

**Open:** A hardness signal that can discriminate frontier problems from each other
(some open problems are "closer" to being solved than others) would require a different
approach — model capability assessment, or a library of known partial results to compare
against.

## Discrimination gap and structural checks (June 2026, beats 912–914)

The decomposability metric exposes a residual ambiguity: **hardness_score = 1.0 can mean
two very different things.** The calibration data contains both:

- `tractable-even-or-odd`: models fully diverge (each picks a different proof strategy for
  the disjunction) → hardness = 1.0. But the problem *is* tractable — the models just found
  distinct valid paths.
- `goldbach`: models diverge because they're confused, not because multiple valid strategies
  exist → hardness = 1.0.

Both score identically. The diversity gate (beat 911, `n_distinct_models`) ensures consensus
requires ≥ 2 distinct model families, but it doesn't resolve the tractable-vs-hard ambiguity
within valid multi-model runs.

### Canonical conjunction check (beat 913)

`Problem.decomposition_type` was already present. Beat 913 added structure-aware extraction:
`_extract_top_level_conjuncts(statement)` parses targets of the form `A ∧ B` into a
`frozenset{A, B}` and `ConsensusResult` carries `canonical_conjuncts` and `n_canonical_match`.

Empirical result on calibration data (`collection-calib-tractable-consecutive-v1.json`,
3 models: gemma4-e2b, phi4, gemma4-e4b):

- **tractable-consecutive** (`∀ n, n ≤ n+1 ∧ 2∣n*(n+1)`): canonical = {n ≤ n+1, 2∣n*(n+1)},
  `n_canonical_match = 2`. phi4 and gemma4-e4b hit the canonical decomposition exactly.
  gemma4-e2b wrapped the divisibility claim in an extra antecedent (`n ≤ n+1 →`) — a
  conjunction misread as an implication, producing a 3-subgoal decomposition that misses
  canonical entirely.
- **tractable-even-or-odd**: canonical = None (target is a disjunction, not a conjunction).
  `n_canonical_match = None`. This is correct — there's no single canonical decomposition
  for a disjunction, so the score isn't applicable.
- **goldbach**: canonical = None (top-level `∀` wraps a complex body; `_extract_top_level_conjuncts`
  rejects non-conjunction tops).

The canonical check is useful precisely where it applies: conjunction targets. It cleanly
surfaces models that confuse conjunctions with implications and produces a concrete
"match rate" signal.

### Key-term soundness heuristic (beat 914)

`Problem.required_predicates` carries Lean identifiers that must appear in any sound
decomposition. `compute_consensus()` accepts `required_predicates` and counts
`n_key_term_absent`: models whose full decomposition text contains none of the required
predicates.

Beat 914's prediction: Goldbach with `required_predicates=["Nat.Prime"]` should show
`n_key_term_absent ≥ 1` because phi4 was observed producing `∃ p q : ℕ, Odd p ∧ Odd q ∧
p + q = n` (wrong predicate substitution). **Calibration baseline falsified this prediction.**

Reprocessing `collection-goldbach-3model-v1.json` (gemma4-e2b, phi4, gemma4-e4b):
- gemma4-e2b: subgoals contain `Nat.Prime` (in a different role — prime divisors, not prime
  summands — but the substring check passes)
- phi4: first subgoal has `Odd p ∧ Odd q`, but *second* subgoal mentions `Nat.Prime n` in a
  factorization context → model-level check passes
- gemma4-e4b: produces `lemma_3` (bare identifier, caught by `is_bare_identifier`) → excluded
  from valid decompositions; diversity gate fires, consensus = None

Result: `n_key_term_absent = 0` for goldbach. The heuristic did not discriminate.

**Why the prediction failed.** The check is per-model and per-decomposition-text — it asks
"does *any* subgoal in this model's decomposition contain the required predicate?" A model can
mention `Nat.Prime` superficially (in a side constraint, in the wrong role) while getting the
structure wrong, and still pass. For Goldbach, a sound decomposition requires `Nat.Prime`
applied to *both summands* in a `p + q = n` structure. Detecting that requires parsing the
Lean expression, not substring matching.

**The discrimination gap is persistent.** Both tractable-even-or-odd and goldbach show:
hardness = 1.0, n_canonical_match = None, n_key_term_absent = 0. No current heuristic
distinguishes them. The only reliable instrument is **Lean verification** — a sound Lean
tactic proof of `subgoal → target` confirms the decomposition is structurally valid, not
just syntactically plausible. This is the next gate in the pipeline.

### Lean reduction auto-verification (beat 916)

`scripts/check_reductions.py` — given a collection run, takes each model's extracted
subgoal types and attempts to auto-close the reduction
`example (h0 : T0) ... (hk : Tk) : target := by <tactic>` in Lean 4 + Mathlib (no sorry).

**Result:** The discrimination signal is confirmed.

| Problem | hardness_score | n_auto_verifiable |
|---|---|---|
| tractable-even-or-odd | 1.0 | **3/3** |
| goldbach | 1.0 | **0/3** |

For `tractable-even-or-odd`: all three models — despite producing structurally different
strategies (trivial implies, induction, step decomposition) — have reductions that close
under `intro n; induction n with | zero => aesop | succ k ih => aesop`. The target has a
short inductive proof; the hypotheses (whatever the model's strategy) provide enough to
close the goal via Mathlib's `aesop` at each step.

For `goldbach`: zero models auto-verifiable.
- gemma4-e2b: prime-factor-existence subgoals don't imply two-prime-summands
- phi4: `Odd p ∧ Odd q` → `Nat.Prime p ∧ Nat.Prime q` is not provable; no tactic closes it
- gemma4-e4b: `∃ p q, ... p + q = 4` (base case) + `∃ p' q', ... p' + q' = n` (specific-n)
  → `∀ n, ...` is not entailed; the hypotheses don't quantify over all even n > 2

**What `n_auto_verifiable` measures**: whether any model found a decomposition whose
hypotheses entail the target via a short Lean proof. For tractable problems, correct
strategies should admit short proofs (their whole point is to be correct subgoals). For
open conjectures, no model can produce a sound, auto-closable reduction (by definition —
if they could, the problem would be solved).

**The discriminating signature**: `hardness_score = 1.0` AND `n_auto_verifiable = 0`
means the divergence is not multi-route tractability — it's genuine hardness or confused
decompositions. This closes the discrimination gap.

**Runs**: `runs/reduction-check-collection-calib-tractable-even-or-odd-v1.json`,
`runs/reduction-check-collection-goldbach-3model-v1.json`.

**Infrastructure**: ren4 (RTX 3090, ELAN_HOME=/models/.elan, 7.2GB prebuilt Mathlib
cache at /models/proving-ground-lean). Mathlib load: 10–86s (cached after first run).
Script at `scripts/check_reductions.py`.
