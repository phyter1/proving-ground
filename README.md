# proving-ground

**A benchmark for LLMs on provably unsolved problems.**

Most benchmarks measure whether a model can reproduce a known answer. This one measures
whether a model can make *verifiable progress on problems humanity has not solved.*

It is built on a single asymmetry: for a large class of mathematical problems, **finding**
a solution is open and hard, but **checking** a candidate is mechanical and certain — the
Lean theorem prover's kernel either accepts a proof or it does not. There is no answer key
to leak, no rubric to argue with, and no way to fake a pass. A high score here is not a
number on a leaderboard; it is a new mathematical fact.

## The problem this solves

Every existing formal-proof benchmark (miniF2F, PutnamBench, DeepMind's `formal-conjectures`)
scores **binary**: the kernel accepts a complete proof, or it doesn't. That's fine for
solved problems. On genuinely *open* problems it produces a wall of zeros — every model,
every method, 0%. A benchmark with no gradient measures nothing.

`proving-ground` introduces a **kernel-verified partial-credit metric**. A model gets
credit for a *verified reduction*: a kernel-checked proof that an open conjecture `C`
follows from a set of named lemmas `L₁ … Lₖ`, plus complete proofs of however many of
those lemmas it can close. Score = the fraction of the decomposition the kernel actually
grounds. Partial progress on the unsolved becomes measurable.

And the lemmas a model *can't* close don't vanish — they're new, smaller open problems,
verified to imply something humans care about, fed straight back into the corpus. **The
benchmark grows itself from partial progress.**

→ Full metric spec: [`docs/SCORING.md`](docs/SCORING.md)

## What's novel here

The corpus of open problems already exists (we reuse DeepMind's `formal-conjectures` and
`SorryDB`). The Lean kernel and the anti-cheat tooling already exist (we reuse `repl`,
`SafeVerify`, `leanchecker`). The unoccupied ground — the thing no benchmark does — is the
**measurement layer**:

1. **Kernel-verified partial credit** on *open* problems (not just solved ones).
2. A **self-renewing difficulty ladder**: progress manufactures easier sub-problems.
3. **Contamination renewal**: even the calibration tier is sourced from lemmas proved
   *after* a model's training cutoff, so a public benchmark stays uncontaminated.

## Status

The full pipeline is scaffolded and tested end to end — **105 tests, no Lean toolchain
required to run them.** The one remaining toolchain-bound piece is the live Lean
verification leaves (clearly marked in `checker.py`), which run on the fleet / in Docker.

```
src/proving_ground/
  models.py       # pure data: Subgoal, Decomposition, Score, Problem, RunResult, Tier
  scoring.py      # the partial-credit metric (fully tested, no Lean needed)
  lean_checker.py # repl/axiom parsing + verdict logic (tested vs canned Lean output)
  checker.py      # Lean integration boundary (repl + SafeVerify); orchestration done,
                  #   subprocess leaves stubbed for the on-fleet milestone
  extract.py      # turn an LLM response into a ProofArtifact
  runner.py       # provider-agnostic model runner (fleet router + cloud, via httpx)
  corpus.py       # ingest formal-conjectures / SorryDB; self-renew from reductions
  results.py      # aggregate RunResults per tier (never blended)
  leaderboard.py  # render markdown + self-contained HTML leaderboard
  cli.py          # `score` and `leaderboard` commands
docs/SCORING.md   # the metric, written down as spec
tests/            # acceptance tests for every module
```

The flow: `corpus` supplies a `Problem` → `runner`/`extract` get a `ProofArtifact` from a
model → `checker` (on the fleet) verifies it into a `Decomposition` → `scoring` assigns a
`Score` → leftover open lemmas `corpus.renew_from_decomposition` back into the corpus →
`results`/`leaderboard` rank the field. Everything except the live Lean verification is
done and tested.

### CLI

```bash
proving-ground score problems/example-reduction.json   # apply the metric to a verdict
proving-ground leaderboard runs.json --out site/        # build the leaderboard
```

### Develop

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
```

## Anti-cheat

"It compiled" is not "it's proven" — `sorry` only warns. Every discharged node must pass:
statement integrity (no goal-tampering), an axiom allowlist (`propext`, `Classical.choice`,
`Quot.sound` only — rejecting `sorryAx` and `native_decide` exploits), and a fresh kernel
re-check. Details in [`docs/SCORING.md`](docs/SCORING.md#the-hard-gates-score-0-if-any-fail).

## Standing on

`google-deepmind/formal-conjectures` · `SorryDB` · `leanprover-community/repl` ·
`GasStationManager/SafeVerify` · `FormalML` · LiveCodeBench / miniCTX. Credit and links in
[`docs/SCORING.md`](docs/SCORING.md#prior-art-we-stand-on-credit-where-due).

## License

Apache-2.0.
