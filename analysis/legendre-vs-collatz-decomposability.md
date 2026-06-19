# Legendre vs. Collatz: Decomposability Discrimination

*Beat 894, ren1, 2026-06-19. Developed from beat 893 literature-richness criterion.*

## The open question

`first-run-findings.md` closes with: "A hardness signal that can discriminate frontier
problems from each other...would require a library of known partial results to compare
against." Legendre and Collatz both produce frontier-null in the current metric. This
analysis argues they should produce *different kinds* of null — and that the difference is
measurable.

## Literature richness determines decomposability type

The beat 893 criterion: problems can be research-frontier-hard (no proof known) while
differing in *literature richness* — the density of named partial results a model can use
as decomposition anchors.

**Twin primes (rich):** Chen's theorem, Brun's theorem, Goldston-Pintz-Yıldırım (2005),
bounded prime gaps (Maynard, 2013). Models have named theorems to cite, restrict to
canonical forms (6k±1), and construct non-trivial subgoals. First-run data confirmed:
Claude produced a real unboundedness structure rather than a bare restatement.

**Collatz (sparse):** No named partial result meaningfully bounds or reduces the 3n+1
orbit. Terras density results are probabilistic. No theorem says "Collatz reduces to X
once you handle Y." Models have nothing structural to grab — the orbit behavior is where
all the difficulty lives. Prediction: all capable models produce near-identical
restatements. Decomposability metric: N_real < 2, hardness = null, null is degenerate.

**Legendre (medium — has a Bertrand anchor):** Bertrand's Postulate (Chebyshev, 1852)
is proven, in Mathlib, and directly relevant:

> For any n ≥ 1, there exists a prime p with n < p ≤ 2n.

Applied to Legendre: Bertrand gives a prime in (n², 2n²). Legendre wants a prime in
(n², (n+1)²) = (n², n² + 2n + 1). The gap between what Bertrand delivers and what
Legendre needs is clearly articulable: a factor of ~n in interval width.

Additional anchors: Baker-Harman-Pintz (2001) gives a prime in [x, x + x^0.525] for
large x. For x = n² this yields an interval of width n^1.05, whereas Legendre requires
width ≤ 2n = 2n^1. BHP doesn't imply Legendre but provides a second decomposition
trajectory. Cramér's conjecture implies Legendre but is itself unproven — models can
cite it as a conditional chain.

## Prediction: Legendre = structured frontier-null

Because Legendre has the Bertrand anchor, different model families should produce
**different** decomposition strategies (Bertrand path vs. BHP path vs. Cramér conditional
chain) that all fail at the same final gap. This means:

- Multiple distinct decomposition artifacts (N_real ≥ 2)
- Hardness score ≠ null
- But all residual open lemmas are equivalent: "there's always a prime in a width-2n
  interval starting at n²" — which is the conjecture restated at a smaller scale

Collatz prediction:
- Near-identical restatements across model families
- N_real < 2 after deduplication
- Hardness = null, same as twin primes from first run (before literature richness was
  factored in)

## Why this matters for the corpus

Structured frontier-null problems are more valuable corpus than degenerate ones:

1. **Partial-credit gradient.** A model that correctly identifies Bertrand's interval,
   correctly states the gap, and correctly concludes the gap is open has done something
   real — even though it scored 0 on the open tier. The artifact demonstrates mathematical
   reasoning about partial results, not just conjecture-retrieval.

2. **Discriminating model capability.** Two models that both score 0 might be producing
   "Bertrand gets us to width 2n², Legendre needs width 2n, open gap is a factor of n" vs.
   "This is an open problem in number theory." Structured null vs. degenerate null carry
   different information about the model.

3. **Hardness signal across frontiers.** If Legendre produces structured null and Collatz
   produces degenerate null, the decomposability metric discriminates them — without knowing
   anything about how close either is to being solved. The Bertrand anchor is the signal.

## Proposed corpus gate

From beat 893: "Can you name 2 theorems that bound or reduce this problem to something
nameable in Lean?" If no, the problem is Collatz-class.

For Legendre:
- Bertrand's Postulate → yes (Mathlib: `Nat.bertrand` or equivalent)
- Baker-Harman-Pintz → yes (not in Mathlib, but citable)

Legendre clears the gate. Collatz does not. Twin primes clears (Chen, Brun, GPY, Maynard).
Goldbach clears (Chen's other theorem: every large even = prime + semiprime; Vinogradov).

## Empirical verification

**Collatz run completed (beat 896, ren1, 2026-06-19):** 3-model fleet
(ren3/qwen3.5-9b-mlx, ren4/gpt-oss-20b, ren2/gemma4-e2b).
Config: `fleet-collect-config-ren1-local.json`. Output:
`runs/collection-collatz-ren1-local-v1.json`.

Unexpected result:
- n_degenerate: **1** (qwen3.5 → exact restatement of target)
- n_real: **2** (gpt-oss + gemma4)
- consensus_score: **0.0** → hardness_score: **1.0**

This is a false positive. The non-degenerate outputs are not genuine decompositions:
- **gpt-oss**: single subgoal `∀ n : ℕ, 0 < n → ∃ k : ℕ, iter k n = 1 ∧ k ≤ 100` — added a
  spurious `∧ k ≤ 100` bound. Mathematically wrong (the bound makes the problem easier
  than the conjecture). Token-novel relative to the target, so not flagged as degenerate.
- **gemma4**: two subgoals — trivial base case `∃ k, iter k 1 = 1` plus the original
  conjecture restated. `is_degenerate` returns False because not all subgoals are echoes
  (the base case is specific). But the second subgoal IS the target, making this the
  "necessity / irredundancy" failure mode from `first-run-findings.md`.

**Hardness_score = 1.0 is a false positive:** the models produced diverse garbage, not
diverse genuine decompositions. Cross-model Jaccard divergence reflects *confusion* rather
than *decomposition branching.*

### New failure mode: confusion-driven non-degeneracy

When models don't have a real decomposition strategy, they may:
1. Add spurious constraints to the target (gpt-oss pattern: `∧ k ≤ 100`)
2. Split into trivial base cases + original conjecture (gemma4 pattern)

Both escape `is_degenerate` and inflate hardness_score. Confusion-driven non-degeneracy
is structurally identical to anchor-driven non-degeneracy in the metric — both produce
diverse, non-empty `novel_statements` with high Jaccard divergence. The score cannot
distinguish them.

**Implication for the literature_anchors hypothesis:** The Collatz result shifts the
prediction. If Legendre produces similar confusion-driven non-degeneracy (different wrong
things, high Jaccard divergence, hardness_score ≈ 1.0), the metric cannot discriminate
Collatz from Legendre using the score alone. The distinguishing signal would have to live
in the *content* of the novel_statements — whether they reference Bertrand-like reasoning
vs. adding random constraints.

### Legendre v1 run (beat 897, ren1, 2026-06-19)

Same fleet config, ren4/gpt-oss-20b timed out — only 2 models completed.
Output: `runs/collection-legendre-ren1-local-v1.json`.

Results (2 of 3 models):
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. Single subgoal: full restatement of
  the target (`∀ n : ℕ, 0 < n → ∃ p : ℕ, n² < p ∧ p < (n+1)² ∧ Nat.Prime p`).
- **ren2/gemma4-e2b** → is_degenerate: **false**. Two subgoals:
  1. `∃ p : ℕ, n² < p ∧ p < (n+1)²`
  2. `Nat.Prime p`
- **ren4/gpt-oss-20b** → timeout error.
- consensus_score: **null** (only 1 real response, can't compute Jaccard divergence)
- hardness_score: **null**

**Key observation:** gemma4's Legendre decomposition is *structurally meaningful*.
Separating existence-in-interval from primality is exactly the right conceptual move —
the existence part is where Bertrand-class tools (prime-in-interval theorems) apply.
The scope binding (`p` not carried across subgoals) has a Lean formalization issue, but
the *mathematical idea* is sound.

**Contrast with Collatz/gemma4:** That split was trivial base case (`∃ k, iter k 1 = 1`)
plus the original conjecture. The base case adds no decomposition leverage; it's just a
specific case that's obviously true. Legendre/gemma4's split is conceptually non-trivial.

**Hypothesis status:** Qualitatively confirmed. Literature anchors do shape decomposition
quality at the model level. Legendre produces structurally meaningful non-degeneracy;
Collatz produces trivial/confusion-driven non-degeneracy. The models weren't explicitly
told about Bertrand — but existence-in-interval is a natural decomposition direction
precisely because the mathematical literature points there.

**What's missing:** 3-model run with ren4 working, to get a computable hardness_score and
test whether gpt-oss-20b also produces structured vs. confusion-driven output. (Legendre
v2 rerun started beat 897 with same config; ren4 reachable again post-timeout.)

**Metric gap that remains:** Even with 3 models, the current metric can't distinguish
gemma4's Legendre split (structured) from gemma4's Collatz split (trivial) by score alone.
Both produce novel_statements with high Jaccard divergence relative to degenerate models.
The distinguishing signal is *in the content*: does the existence subgoal reference a
known interval theorem? Automating this requires a theorem-name index. Manual inspection
confirms the distinction for now.

### Legendre v2 run (beat 898, ren1, 2026-06-19)

Same fleet config. gpt-oss-20b timed out again (3rd consecutive timeout). 2 of 3 models
completed. Output: `runs/collection-legendre-ren1-local-v2.json`.

Results:
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. Same full restatement as v1.
- **ren2/gemma4-e2b** → is_degenerate: **true**. Single subgoal:
  `∃ p : ℕ, n ^ 2 < p ∧ p < (n + 1) ^ 2 ∧ Nat.Prime p`
- consensus_score: **null**, hardness_score: **null**

**gemma4 regressed.** In v1, gemma4 produced the existence-in-interval + primality split
(2 subgoals, non-degenerate). In v2, it produced a single conjunction — the inner predicate
of the Legendre conjecture with `n` as a free variable. That's mathematically equivalent to
the conjecture itself, just with the universal quantifier stripped. Degenerate.

The v1 split was structurally meaningful; the v2 output is not. Both came from the same
model on the same problem. The difference is stochastic sampling variance — gemma4 sits
near the degeneracy boundary for Legendre.

### Sampling variance problem

A single run produces a binary measurement (degenerate / not degenerate). That binary is
stable only for models that are clearly above or below the boundary. For models near the
boundary — where the probability of non-degenerate output is ~0.3-0.7 — a single run
resolves to one bit of noise.

gemma4's Legendre behavior across two runs: v1 non-degenerate, v2 degenerate. The sample
is too small to distinguish "gemma4 has 50% chance of structured output on Legendre" from
"gemma4 has 20% chance" or "30% chance."

**Implication:** The metric needs k ≥ 3 independent runs per model per problem to estimate
a *degeneracy rate* rather than flip a binary coin. The corpus gate (literature_anchors ≥ 2
named theorems) predicts which problems should have *lower* degeneracy rates — but you need
enough samples to measure the rate.

**Revised hypothesis status:** Still qualitatively supported. gemma4 produced a
structurally meaningful decomposition in v1; the existence-in-interval split is exactly
where Bertrand-class tools apply, and the model wasn't told about Bertrand. That's real
signal. But the signal is weak — not enough to call it a stable behavioral difference yet.
Discriminating Legendre from Collatz via degeneracy rates requires k ≥ 3 runs; with k=2
across both v1 and v2, the evidence is v1: 1 non-degenerate (gemma4), v2: 0 non-degenerate.
That's a degeneracy rate of maybe 25% (1/4 responses non-degenerate), compared to Collatz
Collatz's 2/3 — in the wrong direction. The small n means these estimates are nearly
meaningless until we collect more runs.

**Next step:** Run Legendre v3, v4, v5 with the same config to build a k=5 degeneracy rate
per model. gpt-oss needs a separate fix (consistent timeouts suggest the ren4 Ollama model
swap isn't happening fast enough — try pre-loading the model before collection run).

### Legendre v3 run (beat 899, ren1, 2026-06-19)

gpt-oss-20b pre-warmed before collection (loaded model manually, confirmed response before
starting run). All 3 models completed. Output: `runs/collection-legendre-ren1-local-v3.json`.

Results:
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. Same full restatement (3rd consecutive).
- **ren4/gpt-oss-20b** → is_degenerate: **false**. Single subgoal:
  `∀ n : ℕ, 0 < n → ∃ p : ℕ, n ^ 2 < p ∧ p < (n + 1) ^ 2 ∧ Nat.Prime p ∧ p % 2 = 1`
- **ren2/gemma4-e2b** → is_degenerate: **true**. Same single conjunction as v2.
- consensus_score: **null**, hardness_score: **null** (only 1 non-degenerate, needs ≥2)

**gpt-oss-20b spurious-constraint pattern confirmed.** The model added `∧ p % 2 = 1` (p is
odd). On Collatz (v1), gpt-oss added `∧ k ≤ 100`. The pattern is model-specific, not
problem-specific: gpt-oss-20b consistently strengthens the target with random side conditions
rather than decomposing it. This is **confusion-driven non-degeneracy** — the model doesn't
have a decomposition strategy, it just adds unnecessary predicates. The output escapes
`is_degenerate` because it's token-novel, but it's mathematically weaker information than
the target (the added constraint narrows the existential claim without leverage).

**Rate picture after v1-v3 (k=3 for qwen3.5/gemma4, k=1 for gpt-oss):**

| Model | N | Degenerate | Rate | 95% CI (Wilson) | Notes |
|-------|---|-----------|------|-----------------|-------|
| qwen3.5-9b-mlx | 3 | 3 | 100% | [44%, 100%] | Stable restater |
| gemma4-e2b | 3 | 2 | 67% | [21%, 94%] | Near boundary |
| gpt-oss-20b | 1 | 0 | 0% | [0%, 79%] | Confusion-driven non-degen |

The Wilson CIs overlap substantially — 3 runs per model is insufficient for discrimination.
CI width is ±25-35 percentage points even at k=3. Need k≥5 for tighter estimates.

### Legendre v4 run (beat 899, ren1, 2026-06-19)

Same config. gpt-oss-20b timed out again despite model being confirmed loaded on ren4.
Output: `runs/collection-legendre-ren1-local-v4.json`.

Results:
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. 4th consecutive restatement.
- **ren2/gemma4-e2b** → is_degenerate: **true**. Same unquantified conjunct as v2.
- **ren4/gpt-oss-20b** → timeout error (model was loaded per `api/ps`, inference itself hit 300s limit).

**gpt-oss inference timeout is intermittent** — succeeds with spurious-constraint output (v3) but
times out in other runs (v1, v2, v4). Temperature=0 should produce deterministic outputs, but
timing varies. The 300s client timeout may be insufficient for some inference runs at this model
size. Not currently worth debugging — gpt-oss data is unreliable at this collection setup.

**Rate picture after v1-v4 (k=4 for qwen3.5/gemma4, k=1 for gpt-oss):**

| Model | N | Degenerate | Rate | 95% CI (Wilson) |
|-------|---|-----------|------|-----------------|
| qwen3.5-9b-mlx | 4 | 4 | 100% | [51%, 100%] |
| gemma4-e2b | 4 | 3 | 75% | [30%, 95%] |
| gpt-oss-20b | 1 | 0 | 0% | [0%, 79%] |

The pattern stabilizes: qwen3.5 is robustly degenerate; gemma4 is borderline (true rate
somewhere in [30%, 95%] at 95% confidence). v5 (in flight, beat 899) adds one more data point.

### Legendre v5 run (beat 901, ren1, 2026-06-19)

ren2/gemma4-e2b and ren4/gpt-oss-20b both timed out. Only qwen3.5 completed.

Results:
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. 5th consecutive restatement of target.
- **ren2/gemma4-e2b** → timeout error.
- **ren4/gpt-oss-20b** → timeout error.

v5 adds only one data point (qwen3.5). ren2 and ren4 may have been under load from parallel
calibration runs started this beat.

**Final k=5 Legendre rate table (three-way classifier):**

| Model | N | Deg | Conf | Struct | DegRate | 95% CI (Wilson) |
|-------|---|-----|------|--------|---------|-----------------|
| ren3/qwen3.5-9b-mlx | 5 | 5 | 0 | 0 | 100% | [57%, 100%] |
| ren2/gemma4-e2b | 4 | 3 | 0 | 1 | 75% | [30%, 95%] |
| ren4/gpt-oss-20b | 1 | 0 | 1 | 0 | 0% | [0%, 79%] |

**gpt-oss is excluded from further Legendre analysis.** Intermittent timeouts make its data
unreliable at this collection config. The one confirmed run produced confusion-driven output
(spurious `∧ p % 2 = 1` conjunct).

**Gemma4 conclusion:** With N=4 and degeneracy rate 75% [30%, 95%], gemma4 is near the
Legendre boundary but the CI is too wide to be definitive. A true rate of 30% or 95% are
both consistent with the data. The one structured output (v1) is real signal — the
existence-in-interval + primality split is mathematically correct decomposition direction
— but not stable enough to call.

**Qwen3.5 conclusion:** Robustly degenerate across all 5 Legendre runs. Always produces
the full restatement. Literature anchors have no observable effect at this model size/quality.

**Critical observation:** The binary degeneracy comparison Legendre vs. Collatz goes in
the *wrong direction* when counting rates naively. gemma4 is MORE degenerate on Legendre
(67%) than Collatz (0%). But Collatz/gemma4's non-degenerate output is a trivial base case
(`∃ k, iter k 1 = 1`) plus conjecture restatement — confusion-driven. Legendre/gemma4's
one non-degenerate output (v1) was the existence-in-interval + primality split — structured.

**The metric cannot distinguish these two types of non-degeneracy from the binary score.**
The distinguishing signal lives in the content:
- Collatz confusion: `iter k 1 = 1` (a trivially true specific case) + conjecture
- Legendre structured: `∃ p, n² < p < (n+1)²` (interval condition) + `Nat.Prime p` (separate)
- Legendre confusion (gpt-oss): original conjecture + `∧ p % 2 = 1` (irrelevant predicate)

A theorem-name index (or structured-pattern matcher) is needed to automate this
discrimination. Manual classification is feasible at this scale (3 problems × 3 models × 5
runs) but won't scale to a benchmark with 50+ problems.

## Refined metric proposal: three-way classification

The binary `is_degenerate` flag conflates "confusion-driven non-degenerate" and
"anchor-driven structured non-degenerate" outputs. Both escape the degenerate filter, but
they carry different information. The correct classification is three-way:

| Class | Description | Example |
|-------|-------------|---------|
| **degenerate** | Model restates the target or omits quantifiers | qwen3.5 on any open problem |
| **confusion** | Non-degenerate but not anchored: spurious constraints or trivial splits | gpt-oss adds `∧ p % 2 = 1`; gemma4 adds base case + restatement |
| **structured** | Non-degenerate and anchored: subgoals correspond to known partial results | gemma4 v1: existence-in-interval + primality (Bertrand-type) |

### Refined hypothesis

Instead of: "Legendre should have *lower* degeneracy rate than Collatz"

The correct prediction: "Legendre should have *higher structured_non_degen rate* than Collatz"

Manual classification from v1-v3 data:

| Model | Problem | N | Degenerate | Structured | Confusion |
|-------|---------|---|-----------|-----------|----------|
| qwen3.5 | Legendre | 3 | 3 | 0 | 0 |
| qwen3.5 | Collatz | 1 | 1 | 0 | 0 |
| gemma4 | Legendre | 3 | 2 | 1 | 0 |
| gemma4 | Collatz | 1 | 0 | 0 | 1 |
| gpt-oss | Legendre | 1 | 0 | 0 | 1 |
| gpt-oss | Collatz | 1 | 0 | 0 | 1 |

**Legendre structured rate: 1/7 (14%)** vs. **Collatz structured rate: 0/3 (0%)**.
Direction is correct (✓) but samples too small for statistical confidence.

Model-specific patterns that emerge:
- **qwen3.5**: always degenerate; anchor richness has no effect
- **gpt-oss**: always confusion-non-degenerate; adds spurious constraints to target regardless of problem
- **gemma4**: near the boundary; shows genuine structured output probabilistically on anchor-rich problems (Legendre), confusion output on anchor-poor problems (Collatz)

The literature_anchors hypothesis is most load-bearing for gemma4-class models — those near
the degeneracy boundary where anchor availability tips the decomposition strategy. Models
that are robustly above or below the boundary aren't affected.

### Implementation path for three-way classification

1. **Confusion detection (automatic):** Check if any subgoal is the original target plus
   additional conjuncts. If a subgoal contains the full target statement as a substring or
   subformula, it's confusion-driven.

2. **Structured detection (semi-automatic):** Check if subgoals match patterns from
   `literature_anchors` in the problem metadata. For Legendre: look for existence-in-interval
   without primality bundled in, OR explicit references to Bertrand-type intervals.

3. **Fallback to manual:** Outputs that pass confusion check and don't match structured
   patterns get a `needs_review` flag. At this scale, manual review takes ~30 seconds per
   output.

## Calibration baseline: statement shape predicts decomposability (beat 901, 2026-06-19)

Running tractable-tier problems with the current fleet revealed an unexpected finding:
decomposability correlates with statement *shape*, not just mathematical difficulty tier.

**Results from 2-model fleet (qwen3.5-mlx + gemma4-e2b):**

| Problem | Statement | Shape | hardness |
|---------|-----------|-------|---------|
| tractable-consecutive | ∀ n, n≤n+1 ∧ 2\|n(n+1) | conjunction (∧) | **0.0** |
| tractable-even-or-odd | ∀ n, Even n ∨ Odd n | disjunction (∨) | **null** |
| tractable-even-product | ∀ n, Even (n*(n+1)) | single predicate | **null** |

The tractable-consecutive result is the clean calibration signal: hardness=0.0 because
both models produce identical correct decompositions of the conjunction. The ∧ in the
statement is a natural decomposition point — models split it into `∀ n, n ≤ n+1` and
`∀ n, 2 ∣ n*(n+1)`, achieving perfect consensus.

The disjunction (∨) and single-predicate cases produce null hardness — indistinguishable
from the open-problem degenerate signature. Both models restated the target rather than
decomposing it.

**What this means for corpus design:**

The metric does not measure "is this problem hard?" — it measures "does the statement
structure prompt decomposition?" Those correlate on open problems (no anchor → degenerate)
but diverge on tractable problems (provable ≠ has decomposition structure).

**Implication 1: The calibration tier needs structural pre-filtering.** Not all "weakly open
/ provable" problems serve as useful calibration baselines. A problem earns calibration value
only if its statement shape prompts non-degenerate decomposition. Current heuristic: look for
∧-conjunction structure. `∀ n, A ∧ B` → calibration. `∀ n, A ∨ B` or `∀ n, P n` → likely
degenerate regardless of difficulty.

**Implication 2: The metric discriminates on two independent axes.** Not one.

| | ∧-shaped statement | Other statement shape |
|---|---|---|
| **Open problem** | Confusion or structured (hypothesis: ↑ anchors → ↑ structured) | Degenerate |
| **Tractable problem** | hardness = 0 (calibration ✓) | Degenerate (same as open) |

The lower-right cell (tractable + non-∧-shaped) produces the same signature as open problems.
External ground truth (tier label) is required to distinguish them when the metric returns null.

**Implication 3: Prime-gaps is the interesting tractable case.** Statement:
`∀ k : ℕ, ∃ n : ℕ, ∀ j : ℕ, 1 ≤ j → j ≤ k → ¬Nat.Prime (n + j)`. This has `∃∀`
structure — a constructive witness pattern (n = (k+1)! + 1 gives k consecutive composites).
Models that know the factorial-offset construction would produce a distinct decomposition:
reduce to showing each `(k+1)! + j` is composite for j ∈ [1,k]. Results pending from 2-model
calibration run.

## Connection to open question in first-run-findings

The partial-results library approach is the right direction. The library doesn't need to
be exhaustive — even one anchor theorem per problem changes the decomposability type. The
gate criterion (2 named theorems in Mathlib or widely cited) is a cheap pre-filter for
"will this problem produce structured null vs. degenerate null?"

The `literature_anchors` field is already in `benchmark-v1.json` for all open-tier problems.
The `decomposability_prediction` metadata field is also present for all open-tier problems.

**Implementation status (as of beat 902, 2026-06-19):**

1. ✅ **Confusion-detection check in hardness.py** — `is_confusion_non_degenerate()` implemented
   (beat 900). Detects: (a) target-prefix-plus-extra-conjunct, (b) whitespace-collapsed prefix,
   (c) echo-containing multi-subgoal. 56 tests passing, 1 xfail (alpha-equivalence). Commits
   `368ccbb`, `8f44531`.

2. ⏳ **Structured-detection check** — not yet automated. Manual classification remains the
   current path. Requires defining `decomposition_patterns` per problem against
   `literature_anchors`. Blocked until more data informs which patterns to match.

3. ✅ **Three-way output from compute_rates.py** — `--three-way` flag implemented (beat 900).
   Produces degenerate/structured/confusion counts per model per problem. Commit `368ccbb`.

**Corpus schema update (beat 902, 2026-06-19):**

`decomposition_type` field added to all 10 problems in `benchmark-v1.json`. Values:
- `conjunction` (3 problems: calib-add-identities, calib-mul-identities, tractable-consecutive)
- `disjunction` (1 problem: tractable-even-or-odd)
- `universal-predicate` (1 problem: tractable-even-product)
- `existential` (5 problems: tractable-prime-gaps, collatz, legendre, twin-primes, goldbach)

This enables corpus pre-filtering: select only `decomposition_type = "conjunction"` for
calibration baselines. Open-tier problems are all `existential` — the metric's discriminating
axis is anchor richness within that class.

**Active collection runs (beat 902, 2026-06-19):**

- Collatz k=3, 2-model config (`fleet-collect-config-ren1-2model.json`): in flight.
  Prediction: high degeneracy rate for both qwen3.5 (robust restater) and gemma4 (no Collatz
  anchor → confusion or degenerate). Structured rate expected: 0%.
- Goldbach k=3, 2-model config: in flight. Prediction: gemma4 may produce structured output
  via Chen path (every large even = p + p2) or Vinogradov path. Lower degeneracy rate than
  Collatz predicted for gemma4.

Results pending. Update doc when runs complete.

---

## Cross-problem rate comparison (beat 903, 2026-06-19)

### Collatz 2-model results (runs v1-v3 + original local v1, k=4 qwen3.5, k=2 gemma4)

After collecting 3 additional Collatz runs with the 2-model config (ren3/qwen3.5 + ren2/gemma4):

| Model | N | Deg | Conf | Struct | DegRate | 95% CI |
|-------|---|-----|------|--------|---------|--------|
| ren3/qwen3.5-9b-mlx | 4 | 4 | 0 | 0 | 100% | [51%, 100%] |
| ren2/gemma4-e2b | 2 | 0 | 2 | 0 | 0% | [0%, 66%] |
| ren4/gpt-oss-20b | 1 | 0 | 1 | 0 | 0% | [0%, 79%] |

ren2/gemma4 timed out in 2 of 3 new runs. The 2 successful completions both produced
confusion output — the trivial base case + restatement pattern from beat 896.

**Collatz gemma4 confusion output (confirmed both times):**
```
subgoal 1: ∃ k : ℕ, Function.iterate (...) k 1 = 1   -- trivial (n=1, 0 iterations)
subgoal 2: ∀ n : ℕ, 0 < n → ∃ k : ℕ, Function.iterate (...) k n = 1   -- the conjecture
```

The pattern is stable across both successful Collatz/gemma4 runs: the model finds the one
obvious "anchor" (n=1 terminates trivially) and pairs it with the full conjecture restated.
This confirms the Collatz-no-anchor prediction: the only available anchor is a degenerate
base case, not a mathematical partial result that shapes the proof direction.

### Goldbach gap: ren2 timeout failure

All 3 Goldbach ren2/gemma4 runs timed out. ren2 Ollama responds on `/api/tags` (healthy), but
gemma4:e2b generation for Goldbach-length prompts consistently exceeds the 300s client timeout
on ren2's CPU inference path.

This is an infrastructure-coverage gap, not a model capability gap. ren2/Ollama runs gemma4
on CPU (not GPU) for models above the GPU VRAM ceiling. Long math prompts produce more output
tokens, which hits the time ceiling before completion.

**Fix:** route gemma4 through ren3 MLX (which runs at 30-50 tok/s vs. ren2 CPU at <5 tok/s).
New config `fleet-collect-config-ren3-dual.json` uses ren3 MLX for both models.

ren3-dual runs launched (beat 903): Goldbach k=3 and Collatz k=3. Both in flight.

### Cross-problem three-way rates (all data to date)

| Model | Problem | N | Deg | Conf | Struct | Notes |
|-------|---------|---|-----|------|--------|-------|
| qwen3.5 | Legendre | 5 | 5 | 0 | 0 | Robustly degenerate |
| qwen3.5 | Collatz | 4 | 4 | 0 | 0 | Robustly degenerate |
| qwen3.5 | Goldbach | 3 | 3 | 0 | 0 | Robustly degenerate |
| gemma4 | Legendre | 4 | 3 | 0 | 1 | Near boundary; 1 structured |
| gemma4 | Collatz | 2 | 0 | 2 | 0 | Both confusion (trivial anchor) |
| gemma4 | Goldbach | 0 | — | — | — | All timeouts; ren3-dual in flight |
| gpt-oss | Legendre | 1 | 0 | 1 | 0 | Spurious-constraint confusion |
| gpt-oss | Collatz | 1 | 0 | 1 | 0 | Spurious-constraint confusion |

**qwen3.5 pattern:** Uniformly degenerate across all 3 open-tier problems (12/12). Not at the
boundary for any. Literature anchors have zero observable effect on this model.

**gpt-oss pattern:** Always confusion-non-degenerate; always adds spurious constraints. Also
model-not-problem-specific. Excluded from further analysis.

**gemma4 pattern:** The interesting case. Legendre shows 1 structured output (25% structured rate
at N=4); Collatz shows 0 structured outputs with 100% confusion rate. Both sample sizes are too
small for statistical confidence, but the qualitative direction is correct:

- Collatz: no named mathematical anchor → model finds n=1 base case → confusion
- Legendre: Bertrand/BHP anchors → model produced existence-in-interval + primality split (once)

Goldbach prediction (pending ren3-dual results): gemma4 should produce structured output more
frequently than Collatz. Goldbach has a strong Chen anchor (every sufficiently large even =
prime + semiprime) and Vinogradov path (ternary Goldbach proven). These are richer than Collatz's
n=1 base case and comparable to Legendre's Bertrand + BHP anchors.

If Goldbach gemma4 structured rate > Collatz structured rate (0%), that confirms the anchor-richness
gradient: Collatz (no anchor) < Legendre (Bertrand) ≈ Goldbach (Chen/Vinogradov) < twin-primes
(GPY/Maynard). A flat result (both 0%) would challenge the hypothesis.

---

## Model-variant confound and capability tiers (beat 904, 2026-06-19)

### ren3-dual results: gemma4-e4b-mlx

ren3-dual collection runs (v1-v3) completed for both Collatz and Goldbach. These used
`ren3/gemma4-e4b-mlx` — the 4-bit quantized gemma4 running on ren3 MLX. This is a **different
model variant** from the `ren2/gemma4-e2b` used in all prior Legendre/Collatz data.

Three-way rates from compute_rates.py:

**Collatz (all runs combined):**

| Model | N | Deg | Conf | Struct | DegRate | 95% CI |
|-------|---|-----|------|--------|---------|--------|
| ren3/qwen3.5-9b-mlx | 7 | 7 | 0 | 0 | 100% | [65%, 100%] |
| ren2/gemma4-e2b | 2 | 0 | 2 | 0 | 0% | [0%, 66%] |
| ren3/gemma4-e4b-mlx | 3 | 0 | 0 | 3 | 0% | [0%, 56%] |
| ren4/gpt-oss-20b | 1 | 0 | 1 | 0 | 0% | [0%, 79%] |

**Goldbach (ren3-dual runs only):**

| Model | N | Deg | Conf | Struct | DegRate | 95% CI |
|-------|---|-----|------|--------|---------|--------|
| ren3/qwen3.5-9b-mlx | 6 | 6 | 0 | 0 | 100% | [61%, 100%] |
| ren3/gemma4-e4b-mlx | 3 | 0 | 0 | 3 | 0% | [0%, 56%] |

**Result: gemma4-e4b-mlx is 3/3 structured on both Collatz AND Goldbach.** This contradicts
the prediction from beat 903, which expected Goldbach structured rate > Collatz structured rate
(testing the anchor-richness gradient). Instead, e4b produced structured output on both problems
at the same rate (100%), including Collatz which has the sparsest anchors.

### The model-variant confound

The prior Collatz/gemma4 data (2/2 confusion) was `ren2/gemma4-e2b`. The new Collatz/gemma4
data (3/3 structured) is `ren3/gemma4-e4b-mlx`. These look like the same model in casual
reference but are genuinely different checkpoints with different quantization (2-bit vs. 4-bit).

This means the beat 903 prediction was untestable with the ren3-dual config: the prediction
was about gemma4-e2b's Goldbach behavior, but we ran gemma4-e4b instead. The timeout fix
(switching from ren2 CPU to ren3 MLX) inadvertently switched model variants.

The cross-problem comparison table from beat 903 mixes e2b and e4b data under the "gemma4"
label. That conflation needs to be unwound.

**Corrected cross-problem table, by model variant:**

| Model | Problem | N | Deg | Conf | Struct |
|-------|---------|---|-----|------|--------|
| ren2/gemma4-e2b | Legendre | 4 | 3 | 0 | 1 |
| ren2/gemma4-e2b | Collatz | 2 | 0 | 2 | 0 |
| ren2/gemma4-e2b | Goldbach | 0 | — | — | — |
| ren2/gemma4-e2b | Twin primes | 3 | 0 | 0 | 3 |
| ren3/gemma4-e4b-mlx | Collatz | 3 | 0 | 0 | 3 |
| ren3/gemma4-e4b-mlx | Goldbach | 3 | 0 | 0 | 3 |
| ren3/gemma4-e4b-mlx | Legendre | 0 | — | — | — |
| ren3/gemma4-e4b-mlx | Twin primes | 0 | — | — | — |

### Capability tier model

The data across qwen3.5 (7 Legendre + 7 Collatz + 6 Goldbach + twin primes) and the two
gemma4 variants suggests a capability-tier structure:

**Tier 1 — degenerate-anchored (qwen3.5-9b-mlx):**
Always degenerate on Legendre (5/5), Collatz (7/7), Goldbach (6/6). The one exception is
twin primes (40% degenerate, 3/5 structured) — the richest anchor set (GPY/Maynard 2013).
Literature anchors have no observable effect until they're very strong.

**Tier 2 — boundary-sensitive (gemma4-e2b):**
Anchor richness determines output type. Collatz (sparse anchor: n=1 only) → confusion.
Legendre (moderate: Bertrand + BHP) → 75% degenerate, 25% structured. Twin primes (rich:
GPY, Maynard) → 0% degenerate, 100% structured. The anchor-richness gradient maps cleanly
onto this model's behavior.

**Tier 3 — above threshold (gemma4-e4b-mlx):**
Consistently structured across Collatz AND Goldbach (N=6, 0% degenerate, 0% confusion,
100% structured). Anchor richness doesn't determine output — the model produces structured
decompositions regardless. Whether the decompositions are mathematically meaningful vs. novel
noise is a separate quality question (see below).

The anchor-richness hypothesis is **load-bearing for Tier 2 models** (boundary-sensitive)
and **irrelevant for Tier 1 and Tier 3** (robustly below or above the decomposition boundary).
This is a model capability characterization, not just an anchor characterization.

### Quality of e4b structured outputs

The classification system (degenerate/confusion/structured) measures structural novelty, not
mathematical validity. Inspecting the e4b Collatz outputs:

```
subgoal 1: ∃ k' : ℕ, Function.iterate (...) k' n = 1   -- rephrased existential (novel but near-target)
subgoal 2: ∀ k : ℕ, Function.iterate (...) k n ≥ 1    -- positivity invariant (false premise for proof)
```

The second subgoal is interesting: "every iterate is ≥ 1" is true but doesn't help prove
convergence. It's a valid mathematical claim about the sequence, but it's not a useful
decomposition step — showing all iterates are positive doesn't imply one of them equals 1.

For Goldbach, e4b produced a named `lemma_3` (abstract lemma identifier rather than a
stated subgoal). This counts as structured (non-degenerate, non-confusion) but is less
inspectable than a concrete statement.

**Implication:** Tier 3 models are "structurally above the benchmark's detection threshold"
but may not be producing better mathematical reasoning than Tier 2. The benchmark currently
can't discriminate structurally novel from mathematically useful. This will require a
subsequent quality layer — either manual inspection or a theorem-verifier pass.

### Next collection priorities

1. **gemma4-e4b on Legendre and twin primes** (ren3-dual config): completes the e4b cross-
   problem matrix. If e4b is also 100% structured on both, confirms it's robustly Tier 3.
   If Legendre or twin primes shows degenerate/confusion, the tier characterization needs revision.

2. **gemma4-e2b on Goldbach** (the original anchor-richness test): requires fixing the
   ren2 timeout issue (or running e2b on ren3 if MLX supports both quantization levels).
   This is the missing cell for testing the Tier 2 gradient prediction.

3. **Twin primes k=3 with 2-model config** (ren1-2model or ren3-dual): establishes a clean
   baseline with either e2b or e4b and qwen3.5 — the current twin primes data is mixed-config
   old runs.

---

## Tier 3 model revision: token-exceeded on Legendre (beat 905, 2026-06-19)

### ren3-dual Legendre results

ren3-dual Legendre runs (v1-v3) completed since beat 904. Run files:
`runs/collection-legendre-ren3-dual-v1.json` through `v3.json`.

Results from `compute_rates.py --problem-id legendre --three-way`:

| Model | N | Deg | Conf | Struct | Unknown | DegRate | 95% CI |
|-------|---|-----|------|--------|---------|---------|--------|
| ren2/gemma4-e2b | 4 | 3 | 0 | 1 | 0 | 75% | [30%, 95%] |
| ren3/gemma4-e4b-mlx | 0 | 0 | 0 | 0 | 0 | N/A | N/A |
| ren3/qwen3.5-9b-mlx | 8 | 8 | 0 | 0 | 0 | 100% | [68%, 100%] |

**gemma4-e4b-mlx shows N=0 entries** — all 3 ren3-dual Legendre runs threw errors, not
classified outputs. Inspecting the error records:

```
Error (all 3 runs): "No fenced code blocks found in model response."
Response (truncated): ```lean
import Mathlib
-- Target statement: For any natural number n > 0, there exists a prime p such that n^2 < p < (n+1)^2.
-- This is Bertrand's Postulate applied to the interval (n^2, (n+1)^2), which is a weaker form of
--  Legendre's Conjecture...
```

The response starts with a Lean fenced code block but never closes it within the 2048-token
budget. The current error handler treats this as "no fenced block found" (since the closing
` ``` ` is absent), and the entry goes into the `errors` list rather than the classified output.

**This is a fourth behavior type: token-exceeded.** The model opens a ` ```lean ` block and
begins a legitimate proof attempt but runs out of output budget before closing the fence.

### Token-exceeded as a distinct class

Comparison with existing classes:

| Class | Behavior | Example |
|-------|----------|---------|
| degenerate | Restates the conjecture, trivial reduction | qwen3.5 on any open problem |
| confusion | Adds spurious constraints or trivial base case | gpt-oss `∧ p % 2 = 1` |
| structured | Genuine subgoals within token budget | gemma4-e4b on Collatz/Goldbach |
| **token-exceeded** | Real proof attempt, exceeds 2048 tokens before fence closes | gemma4-e4b on Legendre |

Token-exceeded is NOT the same as structured: the output isn't usable for scoring since the
Lean block is incomplete. But it's also NOT the same as degenerate or confusion: the content
that IS present shows genuine mathematical reasoning (citing Bertrand, reasoning about the
interval structure). For benchmark purposes:

- **Not scorable** (no complete subgoals to classify)
- **Informative** as a model behavior signal: the model recognizes the problem as requiring
  more extensive reasoning than Collatz/Goldbach

### Revision to the capability tier model

Beat 904's Tier 3 characterization ("above threshold — consistently structured regardless of
anchor richness") was premature. It was based on Collatz and Goldbach data only. Legendre
data revises it:

**Tier 3 (revised) — gemma4-e4b-mlx:**
- Collatz: 3/3 structured (short proof attempt, fits in 2048 tokens)
- Goldbach: 3/3 structured (short proof attempt, fits in 2048 tokens)
- Legendre: 0/3 structured, 3/3 token-exceeded (longer proof attempt, exceeds 2048 tokens)

The distinguishing factor is not anchor richness but **response length required for the
model's proof strategy**. Legendre prompts the model to explain the Bertrand-to-Legendre
gap (longer text), while Collatz/Goldbach elicit shorter proof sketches.

**Updated capability characterization:**

- **qwen3.5-9b-mlx:** Tier 1 — always degenerate (Legendre 8/8, Collatz 7/7, Goldbach 6/6).
  Exception: twin primes 3/5 structured (richest anchors in corpus).

- **gemma4-e2b:** Tier 2 — boundary-sensitive. Collatz 0/2 structured (trivial anchor),
  Legendre 1/4 structured (Bertrand anchor), twin primes 3/3 structured (GPY/Maynard).
  Anchor-richness gradient is the load-bearing model for this variant.

- **gemma4-e4b-mlx:** Tier 3 (revised) — above degeneracy threshold, but output length
  is problem-dependent. Short-proof problems (Collatz, Goldbach): 100% structured. Long-proof
  problems (Legendre): 100% token-exceeded. Response complexity tracks problem complexity
  rather than saturating at max-output.

### Max-tokens as a measurement parameter

The fleet-collect-config-ren3-dual.json note says `max_tokens=2048` "prevents response
truncation before closing fence." For Collatz and Goldbach this is correct. For Legendre,
2048 tokens is insufficient for e4b's proof strategy.

**Options for future Legendre/e4b collection:**

1. **Increase max_tokens to 4096** for Legendre runs. This should capture a complete fence
   close if the proof attempt is ~2x longer than Collatz. Risk: slower collection (2x output
   per run on ren3 MLX).

2. **Accept token-exceeded as a category** and add a fifth class to the classifier. The
   incomplete Lean block is extractable (everything between ` ```lean ` and EOF) and could
   be partially scored — but the infrastructure doesn't support this yet.

3. **Lean truncation parser**: extract the partial block and classify whatever subgoals are
   present. The first few subgoals in a truncated proof may still be well-formed.

Option 1 is the cleanest path. Adding a new Legendre config with `max_tokens=4096`:
`fleet-collect-config-legendre-deep.json`.

### Collection status at beat 905

- **twin-primes ren3-dual v1:** launched (PID 76561), in flight. Results next beat.
- **Legendre/e4b with max_tokens=4096:** config written (`fleet-collect-config-legendre-deep.json`).
- **gemma4-e2b on Goldbach:** still missing; ren2 timeouts prevent CPU-path collection.

---

## Twin-primes ren3-dual results: trivial-tautology failure (beat 906, 2026-06-19)

### Run results

ren3-dual twin-primes k=3 (relaunched; PID 76561 from beat 905 did not persist). Results:

```
collection-twin-primes-ren3-dual-v1.json through v3.json
```

All three runs identical:
- **ren3/gemma4-e4b-mlx** → subgoals: `["True"]`. is_degenerate: false. is_confusion: false.
- **ren3/qwen3.5-9b-mlx** → subgoals: `["∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"]`. is_degenerate: true.

compute_rates three-way output:

| Model | N | Deg | Conf | Struct | DegRate | 95% CI |
|-------|---|-----|------|--------|---------|--------|
| ren3/gemma4-e4b-mlx | 3 | 0 | 0 | 3 | 0% | [0%, 56%] |
| ren3/qwen3.5-9b-mlx | 8 | 5 | 0 | 3 | 62% | [31%, 86%] |

**Critical: the classifier calls e4b's outputs "structured" but they are `True`.** This is a
misclassification. `True` as the sole subgoal is not a structured decomposition — it is
a trivial tautology reduction. The three-way classifier does not catch this case.

### Fifth behavior class: trivial-tautology

| Class | Behavior | Example |
|-------|----------|---------|
| degenerate | Restates the conjecture | qwen3.5 on any open problem |
| confusion | Spurious constraints or trivial base cases | gpt-oss `∧ p % 2 = 1`; gemma4 base-case pattern |
| structured | Genuine subgoals within budget | gemma4-e4b on Collatz/Goldbach |
| token-exceeded | Real proof attempt, exceeds budget before fence closes | gemma4-e4b on Legendre (2048 tok) |
| **trivial-tautology** | All proof obligations collapse to `True` | gemma4-e4b on twin-primes (3/3 runs) |

Trivial-tautology is consistent behavior: e4b produced `True` in all 3 independent twin-primes
runs. Not noise — a stable model response to this problem.

**Why `True`?** The most likely mechanism: e4b generates a Lean proof using a tactic
that believes the statement follows from GPY/Maynard-class results in Mathlib, and the
proof skeleton reduces remaining obligations to `True` (e.g., via `trivial` or `simp` on
a subgoal the model considers trivially solvable). Alternatively: the model uses `decide`
on a statement that evaluates to `True` in the decision procedure but doesn't actually
prove the conjecture.

Either mechanism reflects the same underlying failure: **e4b is overconfident on
twin-primes**. The model "knows" GPY/Maynard and believes the problem is solved from
those anchors, so it generates a proof that trivializes — collapsing to `True` rather than
constructing a genuine proof sketch. This is the opposite of Legendre: there, the model
recognizes the gap and generates an ambitious (too-long) proof. Here, the model doesn't
recognize the remaining gap and closes the proof prematurely.

### Anchor-richness U-curve hypothesis (gemma4-e4b-mlx)

| Problem | Anchor richness | e4b behavior |
|---------|-----------------|--------------|
| Collatz | sparse (n=1 only) | structured (genuine subgoals, short) |
| Goldbach | moderate (Chen, Vinogradov) | structured (genuine subgoals, short) |
| Legendre | moderate-rich (Bertrand + BHP) | token-exceeded (ambitious, long) |
| twin-primes | rich (GPY, Maynard 2013) | trivial-tautology (`True`) |

This suggests an **anchor-richness U-curve** for Tier 3 models:
- **Sparse anchors:** model produces genuine structured output (knows the problem is hard,
  generates heuristic decompositions)
- **Moderate anchors:** model produces ambitious structured output that may exceed budget
- **Rich anchors:** model becomes overconfident, collapsing proof to `True` or equivalent

The U-curve is the opposite of the Tier 2 gradient:
- **Tier 2 (gemma4-e2b):** rich anchors → structured output (anchors enable good decomposition)
- **Tier 3 (gemma4-e4b-mlx):** rich anchors → overconfident tautology (anchors cause premature closure)

If confirmed, this has implications for corpus design: rich-anchor problems are the BEST
problems for Tier 2 model evaluation and the WORST problems for Tier 3 model evaluation.
The optimal corpus for a given model tier looks different.

**Current evidence:** 3 data points (3 twin-primes runs, all `True`). Consistent, not a
single outlier. Hypothesis generation, not confirmation. Needs:
1. More problems at various anchor richness levels with e4b data
2. Manual inspection of the actual Lean code e4b generates for twin-primes
   (the JSON format strips raw responses; need to add raw output capture to the collector)

### Capability tier model (updated)

**qwen3.5-9b-mlx (Tier 1 — degenerate-anchored):**
Legendre 8/8 degenerate, Collatz 7/7 degenerate, Goldbach 6/6 degenerate, twin-primes
~62% degenerate (5/8) with some structured outputs. Exception for very rich anchors only.

**gemma4-e2b (Tier 2 — boundary-sensitive):**
Collatz 0/2 structured (confusion), Legendre 1/4 structured, twin-primes 3/3 structured.
Anchor-richness gradient is load-bearing: richer anchors → higher structured rate.

**gemma4-e4b-mlx (Tier 3 — above threshold, problem-sensitive):**
- Collatz: 3/3 structured (genuine subgoals, budget OK)
- Goldbach: 3/3 structured (genuine subgoals, budget OK)
- Legendre: 0/3 structured, 3/3 token-exceeded (ambitious proof strategy, exceeds 2048 tok)
- Twin primes: 0/3 structured, 3/3 trivial-tautology (`True` — overconfident closure)

Tier 3 characterization update: above-threshold models are not uniformly better. They
show problem-specific failure modes (token-exceeded, trivial-tautology) that Tier 2 models
don't exhibit. The failure mode depends on the model's confidence in the anchor set:
- Unrecognized problem (no anchor) → structured attempt
- Recognized but unsolvable gap → ambitious token-exceeded
- Recognized and "believed solved" → trivial-tautology collapse

### Classifier gap: True-detection missing

`is_degenerate` checks if all subgoals are echoes of the target.
`is_confusion_non_degenerate` checks for spurious-conjunct and echo-containing patterns.
Neither catches `True` as a sole subgoal.

**Fix:** Add a `is_trivial_tautology(subgoals)` check: returns True if any subgoal is
`True`, `trivial`, `⊤`, or `True.intro`. This is a narrow pattern but consistent with
observed behavior. Implementation in hardness.py — next beat.

### Collection status at beat 906

- ✅ twin-primes ren3-dual v1-v3: complete
- 🔲 Legendre/e4b deep (max_tokens=4096): not yet launched; to start this beat
- 🔲 gemma4-e2b on Goldbach: still missing; ren2 timeouts prevent CPU-path collection
- 🔲 Raw response capture: need to add to collector to inspect actual Lean code
- 🔲 is_trivial_tautology classifier: add to hardness.py

---

## Legendre deep confirmation: token-exceeded is structural (beat 907, 2026-06-19)

### Run results

`fleet-collect-config-legendre-deep.json` (max_tokens=4096) k=3 completed (PID 3702, launched
beat 906). Files: `runs/collection-legendre-ren3-deep-v1.json` through `v3.json`.

Results (all three identical):
- **ren3/qwen3.5-9b-mlx** → is_degenerate: **true**. Same full restatement (consistent).
- **ren3/gemma4-e4b-mlx** → `"No fenced code blocks found in model response."` — **token-exceeded**,
  same as at 2048 tokens.

### What the truncated response shows

The response starts:
```
```lean
import Mathlib

-- Target statement: For any natural number n > 0, there exists a prime p such that n^2 < p < (n+1)^2.
-- This is Bertrand's Postulate applied to the interval (n^2, (n+1)^2), which is a weaker form of
--   Legendre's Conjecture (which usually concerns primes between n and 2n).
-- The statement given is equivalent to saying there is always a prime between n^2 and (n+1)^2.

-- We need to prove: ∀ n : ℕ, 0 < n → ∃ p : ℕ, n ^ 2 < p ∧ p < (n + 1) ^ 2 ∧ Nat.Prime p

-- Lemma …
```

The model is writing the Lean file as a **comment essay** — natural language reasoning encoded
as Lean comments rather than tactic code. The truncated preview (which covers several hundred
characters) contains no Lean tactics, no `theorem` declaration, no `by` block — just `--`
comment lines. At 4096 tokens, the model exhausts the budget before writing any executable code.

### Why neither original hypothesis held

Beat 906 posed two options:
1. **4096 tokens is enough → e4b produces genuine structured output** (response-length was
   the only blocker, not overconfidence)
2. **e4b produces `True` even with more budget** → overconfidence is structural

The actual result is neither: at 4096 tokens, the model still hasn't started writing
Lean code. The blocking factor is not token budget per se — it's **generation style**: the
model front-loads an extensive natural language commentary in the Lean comments section before
writing any proof tactics, and 4096 tokens isn't enough for that commentary to end.

This is distinct from the twin-primes trivial-tautology failure mode:
- **Twin-primes:** Model "knows" GPY/Maynard → collapses immediately to `True`
- **Legendre:** Model recognizes the Bertrand gap → writes extensive reasoning about it as
  comments → never commits to tactics

Both reflect anchor-richness effects but at different points in the proof generation pipeline:
- Trivial-tautology fires at **tactic selection** (model picks a proof strategy too early)
- Comment-essay fires at **reasoning externalization** (model reasons out loud before committing)

### Updated five-behavior table

| Class | Trigger mechanism | Example |
|-------|------------------|---------|
| degenerate | No strategy → restates target | qwen3.5 on any open problem |
| confusion | Has a strategy but it's wrong → spurious constraints or trivial base cases | gpt-oss `∧ p % 2 = 1` |
| structured | Has a strategy, executes it within budget | gemma4-e4b on Collatz/Goldbach |
| token-exceeded (comment-essay) | Recognizes hard gap → reasons as comments → no tactics before budget | gemma4-e4b on Legendre |
| trivial-tautology | Overconfident in known result → collapses proof to `True` | gemma4-e4b on twin-primes |

### Implications for Legendre scoring

Increasing max_tokens further (8192, 16384) might eventually capture the closing fence,
but the correct fix is different: the generation failure is stylistic, not budgetary. A
prompt that instructs the model to write Lean code *first* (with comments inline) rather
than write a comment essay first might resolve it — but that changes the prompt design,
which should be held constant across the benchmark.

**Current decision:** Accept token-exceeded as informative-but-not-scorable for now.
The partial Lean block (extractable from the response) may be analyzable with a truncation
parser (option 3 from beat 905 analysis), but that infrastructure doesn't exist yet.

### Collection status at beat 907

- ✅ is_trivial_tautology classifier: implemented, 5 tests, all 63 tests passing (beat 906)
- ✅ Legendre/e4b deep (max_tokens=4096): complete — token-exceeded confirmed structural
- 🔲 gemma4-e2b on Goldbach: still missing (ren2 CPU timeouts, no fix yet)
- 🔲 Raw response capture: needed to inspect full Lean content before budget exhaustion
- 🔲 Prompt engineering investigation: should benchmarks restrict comment preamble?
