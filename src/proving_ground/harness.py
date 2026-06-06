"""The benchmark orchestrator: tie runner -> checker -> scorer -> results together.

Everything else is a stage; this is the loop. It is deliberately dependency-injected — a
``ModelRunner`` and a ``LeanChecker`` are passed in — so the whole pipeline can be
exercised end to end with fakes (no network, no Lean toolchain) and run for real by
swapping in :class:`~proving_ground.runner.OpenAICompatibleRunner` and
:class:`~proving_ground.checker.LeanInteractChecker`.

Clocks are injected too: the harness never calls ``datetime.now()`` itself, so runs are
reproducible and testable. Pass a ``clock`` returning an ISO-8601 string.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from proving_ground.checker import LeanChecker
from proving_ground.corpus import renew_from_decomposition
from proving_ground.extract import ExtractionError
from proving_ground.models import Problem, RunResult, Tier
from proving_ground.runner import ModelRunner, attempt, to_run_result
from proving_ground.scoring import score_decomposition

Clock = Callable[[], str]


@dataclass(frozen=True)
class BenchmarkRun:
    """The output of a benchmark run.

    Attributes:
        results: One :class:`RunResult` per (model, problem) attempted.
        renewed: New problems manufactured from verified reductions — the self-renewing
            engine's output, ready to extend the corpus on the next run.
        errors: ``(problem_id, message)`` for attempts that failed before scoring
            (extraction or runner errors). Surfaced, never swallowed.
    """

    results: tuple[RunResult, ...]
    renewed: tuple[Problem, ...]
    errors: tuple[tuple[str, str], ...]


def run_benchmark(
    problems: Iterable[Problem],
    runner: ModelRunner,
    checker: LeanChecker,
    *,
    clock: Clock,
    renew: bool = True,
    renew_tier: Tier = Tier.WEAKLY_OPEN,
) -> BenchmarkRun:
    """Run ``runner`` against every problem, verify with ``checker``, score, aggregate.

    For each problem: prompt the model, extract a :class:`ProofArtifact`, verify it into a
    :class:`Decomposition`, score it, and (if ``renew``) turn any kernel-verified leftover
    open lemmas into new problems. Failures in attempt/extraction are recorded in
    ``errors`` rather than aborting the whole run — one bad model response should not sink
    the batch.
    """
    results: list[RunResult] = []
    renewed: list[Problem] = []
    errors: list[tuple[str, str]] = []

    for problem in problems:
        try:
            artifact = attempt(problem, runner)
            decomposition = checker.check(artifact)
        except ExtractionError as exc:
            errors.append((problem.id, f"extraction: {exc}"))
            continue
        except Exception as exc:  # noqa: BLE001 - record per-problem, don't abort the batch
            errors.append((problem.id, f"{type(exc).__name__}: {exc}"))
            continue

        score = score_decomposition(decomposition)
        results.append(
            to_run_result(
                problem=problem,
                model=runner.name,
                score=score,
                timestamp=clock(),
            )
        )

        if renew:
            renewed.extend(
                renew_from_decomposition(
                    decomposition, parent_problem_id=problem.id, tier=renew_tier
                )
            )

    return BenchmarkRun(
        results=tuple(results),
        renewed=tuple(renewed),
        errors=tuple(errors),
    )
