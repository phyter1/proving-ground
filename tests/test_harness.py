"""End-to-end test of the orchestrator with fakes — no network, no Lean toolchain.

This is the proof that every stage composes: corpus Problem -> runner -> extract ->
checker -> score -> renew -> RunResult, with failures recorded rather than fatal.
"""

from __future__ import annotations

import pytest

from proving_ground.checker import LeanChecker, ProofArtifact, RecordingChecker
from proving_ground.harness import run_benchmark
from proving_ground.models import Decomposition, Problem, Subgoal, Tier
from proving_ground.runner import ModelRunner


class _FakeRunner(ModelRunner):
    """Returns a canned response containing a parseable Lean block + manifest."""

    name = "fake-model"

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages):  # noqa: ANN001
        return self._response


_GOOD_RESPONSE = """\
Here is my reduction.

```lean
import Mathlib
theorem target : True := by trivial
lemma L1 : True := by trivial
lemma L2 : True := by sorry
```

```json
{"subgoal_ids": ["L1", "L2"]}
```
"""


def _clock():
    return "2026-06-06T12:00:00Z"


def _problem(pid: str, tier: Tier = Tier.OPEN) -> Problem:
    return Problem(id=pid, statement="True", tier=tier, source="test", title=pid)


def _partial_decomp(target_id: str) -> Decomposition:
    # L1 discharged, L2 open; gates pass -> score 0.5, one renewed lemma.
    return Decomposition(
        target_id=target_id,
        target_statement="True",
        subgoals=(
            Subgoal("L1", "lemma1", discharged=True),
            Subgoal("L2", "lemma2", discharged=False),
        ),
        root_implication_verified=True,
        statement_matches_target=True,
        axioms_clean=True,
    )


def test_full_pipeline_scores_and_renews():
    problem = _problem("conj-1")
    runner = _FakeRunner(_GOOD_RESPONSE)
    checker = RecordingChecker(_partial_decomp("conj-1"))

    run = run_benchmark([problem], runner, checker, clock=_clock)

    assert len(run.results) == 1
    result = run.results[0]
    assert result.model == "fake-model"
    assert result.problem_id == "conj-1"
    assert result.tier is Tier.OPEN
    assert result.score.value == pytest.approx(0.5)
    assert result.timestamp == "2026-06-06T12:00:00Z"

    # The self-renewing engine: the one open lemma becomes a new problem.
    assert len(run.renewed) == 1
    assert run.renewed[0].statement == "lemma2"
    assert run.renewed[0].tier is Tier.WEAKLY_OPEN
    assert run.renewed[0].source == "self-renewed"

    assert run.errors == ()


def test_runner_failure_is_recorded_not_fatal():
    problems = [_problem("ok"), _problem("bad")]

    class _SometimesBad(ModelRunner):
        name = "flaky"

        def complete(self, messages):  # noqa: ANN001
            return _GOOD_RESPONSE  # extraction always works; checker differentiates

    class _CheckerThatFailsOnBad(LeanChecker):
        def check(self, artifact: ProofArtifact) -> Decomposition:
            if artifact.target_id == "bad":
                raise RuntimeError("toolchain exploded")
            return _partial_decomp(artifact.target_id)

    run = run_benchmark(problems, _SometimesBad(), _CheckerThatFailsOnBad(), clock=_clock)

    assert len(run.results) == 1
    assert run.results[0].problem_id == "ok"
    assert len(run.errors) == 1
    assert run.errors[0][0] == "bad"
    assert "toolchain exploded" in run.errors[0][1]


def test_extraction_failure_is_recorded():
    problem = _problem("no-lean")
    runner = _FakeRunner("I refuse to produce any Lean code.")
    checker = RecordingChecker(_partial_decomp("no-lean"))

    run = run_benchmark([problem], runner, checker, clock=_clock)

    assert run.results == ()
    assert len(run.errors) == 1
    assert run.errors[0][0] == "no-lean"
    assert "extraction" in run.errors[0][1]


def test_renew_can_be_disabled():
    run = run_benchmark(
        [_problem("c")],
        _FakeRunner(_GOOD_RESPONSE),
        RecordingChecker(_partial_decomp("c")),
        clock=_clock,
        renew=False,
    )
    assert run.renewed == ()
    assert len(run.results) == 1
