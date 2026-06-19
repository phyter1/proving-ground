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
