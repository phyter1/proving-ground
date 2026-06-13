"""End-to-end test of the orchestrator with fakes — no network, no Lean toolchain.

This is the proof that every stage composes: corpus Problem -> runner -> extract ->
checker -> score -> renew -> RunResult, with failures recorded rather than fatal.
"""

from __future__ import annotations

import pytest

from proving_ground.checker import LeanChecker, ProofArtifact, RecordingChecker
from proving_ground.harness import CollectionRun, collect_decompositions, run_benchmark
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


# ── collect_decompositions tests ──────────────────────────────────────────────


class _NamedFakeRunner(ModelRunner):
    """FakeRunner with a configurable name."""

    def __init__(self, name: str, response: str = _GOOD_RESPONSE) -> None:
        self.name = name
        self._response = response

    def complete(self, messages):  # noqa: ANN001
        return self._response


class _MultiDecompChecker(LeanChecker):
    """Returns distinct Decompositions per (runner_name, problem_id) pair."""

    def __init__(self) -> None:
        self._call_index = 0

    def check(self, artifact: ProofArtifact) -> Decomposition:
        self._call_index += 1
        stmt = f"lemma_{self._call_index}"
        return Decomposition(
            target_id=artifact.target_id,
            target_statement="True",
            subgoals=(Subgoal(f"G{self._call_index}", stmt, discharged=False),),
            root_implication_verified=True,
            statement_matches_target=True,
            axioms_clean=True,
        )


def test_collect_two_runners_two_problems():
    problems = [_problem("p1"), _problem("p2")]
    runners = [_NamedFakeRunner("r1"), _NamedFakeRunner("r2")]
    checker = _MultiDecompChecker()

    crun = collect_decompositions(problems, runners, checker)

    assert isinstance(crun, CollectionRun)
    assert crun.errors == ()
    # Two problems, each with 2 decompositions (one per runner).
    assert len(crun.decompositions) == 2
    pid_map = dict(crun.decompositions)
    assert len(pid_map["p1"]) == 2
    assert len(pid_map["p2"]) == 2


def test_collect_decompositions_for_lookup():
    problems = [_problem("alpha")]
    runners = [_NamedFakeRunner("r1"), _NamedFakeRunner("r2")]
    crun = collect_decompositions(problems, runners, _MultiDecompChecker())

    assert len(crun.decompositions_for("alpha")) == 2
    assert crun.decompositions_for("missing") == ()


def test_collect_runner_failure_recorded_not_fatal():
    problems = [_problem("good"), _problem("bad")]

    class _PatchedChecker(LeanChecker):
        def check(self, artifact: ProofArtifact) -> Decomposition:
            if artifact.target_id == "bad":
                raise RuntimeError("lean exploded")
            return _partial_decomp(artifact.target_id)

    runner = _NamedFakeRunner("r1")
    crun = collect_decompositions(problems, [runner], _PatchedChecker())

    assert len(crun.errors) == 1
    assert crun.errors[0] == ("r1", "bad", "RuntimeError: lean exploded")
    assert len(crun.decompositions_for("good")) == 1
    assert len(crun.decompositions_for("bad")) == 0


def test_collect_extraction_failure_recorded():
    runner = _NamedFakeRunner("r1", response="no lean block here")
    crun = collect_decompositions(
        [_problem("p")], [runner], RecordingChecker(_partial_decomp("p"))
    )

    assert len(crun.errors) == 1
    assert crun.errors[0][0] == "r1"
    assert crun.errors[0][1] == "p"
    assert "extraction" in crun.errors[0][2]


def test_collect_preserves_runner_order():
    problems = [_problem("q")]
    call_order: list[str] = []

    class _OrderTrackingRunner(ModelRunner):
        def __init__(self, name: str) -> None:
            self.name = name

        def complete(self, messages):  # noqa: ANN001
            call_order.append(self.name)
            return _GOOD_RESPONSE

    runners = [_OrderTrackingRunner("first"), _OrderTrackingRunner("second")]
    collect_decompositions(problems, runners, _MultiDecompChecker())

    assert call_order == ["first", "second"]
