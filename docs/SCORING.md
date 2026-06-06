# The Scoring Model

This is the part of `proving-ground` that does not exist anywhere else, so it is the
part that has to be exactly right. Everything else (the Lean corpus, the kernel, the
anti-cheat) is reused from existing, battle-tested tooling. The metric is ours.

## The problem with every existing formal benchmark

Every formal-theorem-proving benchmark in existence scores **binary**: the Lean kernel
either accepts a complete proof or it does not. That works fine for *solved* problems
with reference proofs (miniF2F, PutnamBench). It is useless for *open* problems, because
nobody — no human, no model — can produce a complete proof. On DeepMind's
`formal-conjectures` open set, every model and every method scores **0%**. A benchmark
where everyone gets zero has no gradient, and a benchmark with no gradient measures
nothing.

We are not in the business of asking "did you solve this unsolved problem." We are in the
business of asking **"how much verifiable progress did you make on it."**

## The unit of progress: a verified reduction

A mathematician rarely solves an open problem in one move. They *reduce* it: "Conjecture
`C` holds if these three lemmas hold," and then they prove some of the lemmas and leave
the rest open. That reduction is real, checkable, cumulative progress even when `C`
remains open.

We make that the scoring primitive. A **submission** for an open target `C` is a Lean
decomposition consisting of:

1. A set of named **subgoals** `L₁ … Lₖ` (lemmas), each a Lean statement.
2. A **root implication**: a kernel-checked proof that `(L₁ ∧ … ∧ Lₖ) → C`.
3. For each subgoal, either a kernel-checked proof (it is *discharged*) or an explicit
   `sorry` (it remains open).

A submission that discharges every subgoal *is* a complete proof of `C` — score `1.0`.
A submission that discharges some subgoals is partial progress. A submission that
discharges none but still proves the reduction `(L₁ ∧ … ∧ Lₖ) → C` has reformulated the
problem — which may or may not count as progress (see anti-gaming below).

## The submission protocol (how a reduction is expressed in Lean)

A subtlety the live kernel forces, and the reason the protocol looks the way it does:
`#print axioms` is **transitive**. If a model proves the target *directly* from a lemma it
left as `sorry`, then `#print axioms target` reports `sorryAx` — the whole thing looks
unproven, and partial credit collapses back to binary. To verify "the target follows from
the lemmas" *independently* of whether the lemmas are proven, the lemmas must enter the
reduction as **hypotheses**. So a submission is:

```lean
-- each subgoal is its own theorem, proved or left open:
theorem lemma_a : <statement A> := <proof>      -- discharged
theorem lemma_b : <statement B> := by sorry     -- open subgoal

-- the reduction takes the subgoal STATEMENTS as hypotheses and concludes the target:
theorem reduction : (<statement A>) → (<statement B>) → (<frozen target>) := <proof>
```

The checker (`proving_ground.checker.LeanInteractChecker`) then runs, against a live
kernel: `#print axioms lemma_a` (clean ⇒ discharged), `#print axioms reduction` (clean ⇒
the reduction has no `sorry`/`native_decide`), and elaborates
`example : (<A>) → (<B>) → (<frozen target>) := @reduction` (⇒ the reduction genuinely
concludes the *frozen* target with those hypotheses — statement integrity in one check).
This is implemented and verified end to end against Lean 4 / mathlib on the fleet.

## The hard gates (score 0 if any fail)

Before any partial credit is computed, a submission must pass every one of these. These
are not scored on a curve — they are pass/fail, and failing any one means the submission
scores exactly `0.0`. They are what make the number trustworthy.

| Gate | What it checks | Why |
|------|----------------|-----|
| **Statement integrity** | The target theorem's *type and value* are byte-identical to the frozen target spec. | Stops the classic cheat: rewrite `C` into something trivial (e.g. `True`) and "prove" that. (SafeVerify gate C.) |
| **Axiom cleanliness** | `#print axioms` on every discharged node depends only on `{propext, Classical.choice, Quot.sound}`. | Rejects `sorryAx` (sorry-laundering through helper lemmas) and `Lean.trustCompiler` (`native_decide` exploits, which are soundness holes). |
| **Kernel re-check** | Every discharged node survives `leanchecker --fresh` / `Environment.replay`. | `#print axioms` trusts the built environment; metaprogramming can forge an inconsistent one. The kernel replay is the real verdict. |
| **Root implication verified** | `(remaining subgoals) → C` is itself kernel-proven. | A decomposition without a verified implication is just relocating the `sorry`. No logical connection = no progress. |
| **Non-triviality** | No remaining open subgoal is logically equal to the target `C` itself. | Stops the null reduction "`C` follows from `C`." |

## The partial-credit score

If and only if all hard gates pass:

```
score = discharged_weight / total_weight
```

where each subgoal carries a non-negative `weight` (default uniform `1.0`; problems may
ship curated weights reflecting the relative difficulty of each lemma), `total_weight` is
the sum over all subgoals, and `discharged_weight` is the sum over the kernel-discharged
ones.

- All subgoals discharged → `discharged_weight == total_weight` → **`1.0`** (a real,
  publishable proof of an open conjecture).
- Some discharged → a number in `(0, 1)`.
- A pure reduction with nothing discharged → `0.0` *for the scalar*, but the artifact is
  still emitted (see below). We deliberately do **not** award scalar credit for an
  un-grounded reduction in v1, because "how much easier are the new lemmas than the old
  goal" is not something we can measure objectively yet, and we would rather under-claim
  than ship a gameable number. This is documented as an open research direction, not a
  silent omission.

### Honesty about what this measures

`discharged_weight / total_weight` is a **proxy**, and a deliberately conservative one. It
can be inflated by padding a decomposition with many trivial discharged lemmas — which is
why curated per-problem weights exist, and why the *primary* output of the benchmark is
not the scalar but the **artifact** below. We say this out loud rather than pretending the
number is the whole story.

## The self-renewing engine

The most important output of a partial submission is not the score. It is the set of
**remaining open subgoals** `Lᵢ` — each one a Lean statement that has been
kernel-verified to imply (jointly) a known open conjecture, and that no one has yet
proven. Those are *new, smaller open problems*, generated as a byproduct of partial
progress, and they flow back into the corpus as new benchmark entries.

The benchmark grows itself. Progress on a hard problem manufactures a supply of slightly
easier ones, which is exactly the difficulty gradient a benchmark on the frontier needs in
order to stay measurable instead of saturating to all-zero or (eventually) all-one.

## The difficulty ladder (anti-saturation, anti-contamination)

Problems carry a `tier`:

- **`solved_recent`** — theorems with known proofs, used as a calibration / contamination
  canary. Sourced as lemmas proved *after* a model's training cutoff (the LiveCodeBench /
  miniCTX time-window method), so even the "solved" tier is contamination-resistant.
- **`weakly_open`** — open relative to current automated provers but plausibly tractable;
  where the gradient lives today.
- **`open`** — genuinely open conjectures (the `formal-conjectures` open set).

A model that fails `solved_recent` is broken, not challenged. A model that moves the
needle on `weakly_open` is doing something real. A model that scores nonzero on `open` has
made a contribution to mathematics. Reporting is always per-tier — a single blended number
across tiers would be dishonest.

## Prior art we stand on (credit where due)

- `google-deepmind/formal-conjectures` — the open-conjecture corpus and its marking
  conventions (`sorry`, `answer(sorry)`, `@[formal_proof]`).
- `SorryDB` — live harvested real-world `sorry`s + the LeanInteract verification harness.
- `leanprover-community/repl` — JSON proof-checking server.
- `GasStationManager/SafeVerify` + bundled `leanchecker` — the anti-cheat / kernel-replay
  gates.
- `FormalML` — prior art on subgoal-fraction partial credit (on *solved* problems; we
  extend it to *open* ones).
- LiveCodeBench / miniCTX — the time-windowed contamination-resistance method.

Our contribution is the four-way intersection none of them occupy: **open problems +
kernel-verified partial credit + a self-renewing difficulty ladder + contamination
renewal.**
