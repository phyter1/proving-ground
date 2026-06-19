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

This prediction is testable when fleet collection resumes (ENOSPC on ren1 currently
blocking collection runs). Run both Collatz and Legendre through `fleet-collect`, compare
N_real and hardness scores. If the prediction holds:
- Legendre: N_real ≥ 2, hardness ∈ (0, 1)
- Collatz: N_real < 2, hardness = null

If Legendre also produces degenerate null, the Bertrand-anchor hypothesis is wrong and the
literature-richness criterion needs revision.

## Connection to open question in first-run-findings

The partial-results library approach is the right direction. The library doesn't need to
be exhaustive — even one anchor theorem per problem changes the decomposability type. The
gate criterion (2 named theorems in Mathlib or widely cited) is a cheap pre-filter for
"will this problem produce structured null vs. degenerate null?"

Recommended next step: add `literature_anchors` field to benchmark-v1.json entries,
listing named theorems relevant to each problem. This gives the decomposability prediction
before running any collection.
