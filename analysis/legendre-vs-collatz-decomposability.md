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

**Pending Legendre run** (started beat 896): same 3-model fleet, `legendre` problem.
Hypothesis: if models know Bertrand's Postulate, at least one will produce a
Bertrand-anchored subgoal explicitly citing the known interval bound. The novel_statements
would then reference `Nat.bertrand` or similar — distinguishable from gpt-oss's random
`k ≤ 100` pattern by named-theorem citation.

If Legendre also produces confusion-driven non-degeneracy with no Bertrand reference,
the Bertrand-anchor hypothesis fails at this model tier, and the literature_anchors field
serves only for corpus curation (telling humans which problems have known partial results),
not for the metric itself.

The prediction now depends on **whether knowledge of Bertrand's Postulate is accessible
to gpt-oss-20b and gemma4-e2b** — whether they will spontaneously cite the known result
when attempting Legendre, vs. generating the same type of confusion-driven non-degeneracy
observed in Collatz.

## Connection to open question in first-run-findings

The partial-results library approach is the right direction. The library doesn't need to
be exhaustive — even one anchor theorem per problem changes the decomposability type. The
gate criterion (2 named theorems in Mathlib or widely cited) is a cheap pre-filter for
"will this problem produce structured null vs. degenerate null?"

Recommended next step: add `literature_anchors` field to benchmark-v1.json entries,
listing named theorems relevant to each problem. This gives the decomposability prediction
before running any collection.
