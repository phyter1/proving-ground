"""End-to-end demo of the whole benchmark, with no Lean toolchain and no network.

Runs the real pipeline — corpus ingest -> run -> verify -> score -> renew -> leaderboard —
substituting a scripted model and a RecordingChecker (which supplies the verdicts a live
Lean checker would produce). This is what the system does for real; only the two doubles
are fake.

    python examples/demo_pipeline.py
"""

from __future__ import annotations

from proving_ground.checker import ProofArtifact, RecordingChecker
from proving_ground.corpus import parse_formal_conjecture, renew_from_decomposition
from proving_ground.harness import run_benchmark
from proving_ground.leaderboard import render_markdown
from proving_ground.models import Decomposition, Subgoal, Tier
from proving_ground.results import aggregate
from proving_ground.runner import ModelRunner, to_run_result

# 1. INGEST: a formal-conjectures-style source becomes Problems.
LEAN_SOURCE = """\
-- An open conjecture. See https://example.org/conjecture-42
import Mathlib
theorem conjecture_fortytwo (n : ℕ) : Collatzish n → Reaches n 1 := by sorry

-- A recently-proved lemma used for calibration.
theorem helper_lemma (n : ℕ) : n + 0 = n := by simp
"""


class ScriptedModel(ModelRunner):
    """Stands in for an LLM. Returns a fixed decomposition response."""

    name = "demo-model-v1"

    def complete(self, messages):  # noqa: ANN001
        return (
            "I reduce the conjecture to two lemmas and prove the first.\n\n"
            "```lean\nimport Mathlib\n"
            "theorem target : True := by trivial\n"
            "lemma step_a : True := by trivial\n"
            "lemma step_b : True := by sorry\n```\n\n"
            '```json\n{"subgoal_ids": ["step_a", "step_b"]}\n```\n'
        )


# A RecordingChecker plays the role of the Lean kernel: here it certifies that the model
# proved step_a (discharged) and the reduction holds, leaving step_b genuinely open.
def verdict_for(problem_id: str) -> Decomposition:
    return Decomposition(
        target_id=problem_id,
        target_statement="True",
        subgoals=(
            Subgoal("step_a", "the easy half", discharged=True),
            Subgoal("step_b", "the hard half — still open", discharged=False),
        ),
        root_implication_verified=True,
        statement_matches_target=True,
        axioms_clean=True,
    )


class DemoChecker(RecordingChecker):
    def check(self, artifact: ProofArtifact) -> Decomposition:
        return verdict_for(artifact.target_id)


def main() -> None:
    problems = parse_formal_conjecture(LEAN_SOURCE)
    print(f"Ingested {len(problems)} problems:")
    for p in problems:
        print(f"  - {p.id}  [{p.tier.value}]  {p.title}")

    # Deterministic clock for a reproducible demo.
    ticks = iter(f"2026-06-06T12:00:{i:02d}Z" for i in range(60))
    run = run_benchmark(
        problems,
        ScriptedModel(),
        DemoChecker(verdict_for("placeholder")),
        clock=lambda: next(ticks),
    )

    print(f"\nScored {len(run.results)} attempts; {len(run.errors)} errors.")
    for r in run.results:
        print(f"  {r.problem_id}: {r.score.value:.2f} ({r.score.kind.value})")

    print(f"\nSelf-renewed {len(run.renewed)} new open problems from verified reductions:")
    for p in run.renewed:
        print(f"  - {p.id}: {p.statement}")

    # Demonstrate the renewal API directly too.
    extra = renew_from_decomposition(
        verdict_for("conjecture_fortytwo"), parent_problem_id="conjecture_fortytwo"
    )
    assert extra, "a verified reduction should manufacture at least one new problem"

    print("\n--- LEADERBOARD ---\n")
    print(render_markdown(aggregate(run.results)))


if __name__ == "__main__":
    main()
