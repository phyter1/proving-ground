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
swap isn't happening fast enough — try with `OLLAMA_KEEP_ALIVE` or pre-loading the model
before collection run).

## Connection to open question in first-run-findings

The partial-results library approach is the right direction. The library doesn't need to
be exhaustive — even one anchor theorem per problem changes the decomposability type. The
gate criterion (2 named theorems in Mathlib or widely cited) is a cheap pre-filter for
"will this problem produce structured null vs. degenerate null?"

Recommended next step: add `literature_anchors` field to benchmark-v1.json entries,
listing named theorems relevant to each problem. This gives the decomposability prediction
before running any collection.
