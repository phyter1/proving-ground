"""Multi-model collection harness for the cross-model hardness signal.

Collects N independent decompositions for the same problem WITHOUT Lean verification.
The returned Decompositions carry raw extracted type strings suitable for
compute_consensus() — they must never be passed to score_decomposition().

The flow is: runner → ProofArtifact → unverified Decomposition → ConsensusResult.
Verification (checker → scored Decomposition) is a separate path for single-model runs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from proving_ground.checker import ProofArtifact
from proving_ground.extract import ExtractionError
from proving_ground.hardness import ConsensusResult, compute_consensus
from proving_ground.models import Decomposition, Problem, Subgoal
from proving_ground.runner import ModelRunner, RunnerError, attempt

# Bracket-depth type extractor — same logic as corpus._extract_statement; duplicated
# here to avoid importing private symbols from that module.
_OPEN_BRACKETS: dict[str, str] = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
_CLOSE_BRACKETS: frozenset[str] = frozenset(_OPEN_BRACKETS.values())


def _extract_type_from_sig(sig: str) -> str:
    """Pull the Lean type out of a declaration signature.

    *sig* is everything between the declaration name and the ``:=``. The type is
    the text after the first top-level ``:``; ``:`` inside binders (e.g. ``(n : Nat)``)
    are skipped via bracket-depth tracking.
    """
    depth = 0
    for i, ch in enumerate(sig):
        if ch in _OPEN_BRACKETS:
            depth += 1
        elif ch in _CLOSE_BRACKETS:
            depth -= 1
        elif ch == ":" and depth == 0:
            return sig[i + 1 :].strip()
    return sig.strip()


# Match a theorem/lemma declaration body, anchored at the left margin. Non-greedy
# so adjacent declarations are parsed independently. Same pattern as corpus._DECL_RE.
_DECL_RE = re.compile(
    r"""
    ^[^\S\r\n]*                              # optional leading space
    (?:theorem|lemma)\s+                     # declaration keyword
    (?P<name>[A-Za-z_][\w.'!?]*)             # declaration name
    (?P<sig>.*?)                             # binders + ``: TYPE``
    \s*:=\s*                                 # proof body marker
    (?P<body>.*?)                            # proof body (non-greedy)
    (?=^\s*(?:theorem|lemma|@\[|/--|/-|namespace|section|end\b)|\Z)
    """,
    re.VERBOSE | re.DOTALL | re.MULTILINE,
)


def _statements_from_artifact(artifact: ProofArtifact) -> dict[str, str]:
    """Extract raw Lean type strings for each subgoal id in *artifact*.

    Returns a mapping ``{subgoal_id: type_string}``. When a declaration cannot be
    found in the source (parsing failure, unusual syntax), the id itself is used as the
    statement — a degraded but non-crashing fallback.
    """
    found: dict[str, str] = {}
    for m in _DECL_RE.finditer(artifact.lean_source):
        name = m.group("name")
        sig = m.group("sig")
        found[name] = _extract_type_from_sig(sig)

    return {sg_id: found.get(sg_id, sg_id) for sg_id in artifact.subgoal_ids}


def artifact_to_unverified_decomposition(artifact: ProofArtifact) -> Decomposition:
    """Convert a ProofArtifact to an unverified Decomposition for hardness analysis.

    All boolean verification flags are ``False``. Subgoal statements are extracted from
    the Lean source via heuristic regex — close enough for compute_consensus() Jaccard
    comparison, unsuitable for scoring.
    """
    statements = _statements_from_artifact(artifact)
    subgoals = tuple(Subgoal(id=sg_id, statement=stmt) for sg_id, stmt in statements.items())
    return Decomposition(
        target_id=artifact.target_id,
        target_statement=artifact.target_statement,
        subgoals=subgoals,
        root_implication_verified=False,
        statement_matches_target=False,
        axioms_clean=False,
    )


@dataclass(frozen=True)
class CollectionResult:
    """Output of a multi-model collection run for a single problem.

    Attributes:
        problem_id: The problem all models attempted.
        entries: ``(model_name, decomposition)`` pairs, one per successful run.
            Decompositions are unverified — raw extracted type strings only.
        consensus: Cross-model agreement from ``compute_consensus()``. ``None`` when
            every runner failed (no decompositions to compare).
        errors: ``(model_name, message)`` pairs for failed attempts. Surfaced, never
            swallowed — partial collections (errors alongside successful entries)
            are expected when the fleet has mixed availability.
    """

    problem_id: str
    entries: tuple[tuple[str, Decomposition], ...]
    consensus: ConsensusResult | None
    errors: tuple[tuple[str, str], ...]


def collect(
    problem: Problem,
    runners: Sequence[ModelRunner],
) -> CollectionResult:
    """Run all *runners* against *problem* and compute the cross-model hardness signal.

    Each runner is attempted independently. Errors are recorded but do not abort
    the collection — partial results (≥1 decomposition) still yield a consensus score.
    With zero successful runs the consensus is ``None``.

    The returned decompositions are UNVERIFIED; never pass them to
    :func:`~proving_ground.scoring.score_decomposition`.
    """
    entries: list[tuple[str, Decomposition]] = []
    errors: list[tuple[str, str]] = []

    for runner in runners:
        try:
            artifact = attempt(problem, runner)
            decomp = artifact_to_unverified_decomposition(artifact)
            entries.append((runner.name, decomp))
        except (RunnerError, ExtractionError) as exc:
            errors.append((runner.name, str(exc)))
        except Exception as exc:  # noqa: BLE001 — per-runner failure should not abort the batch
            errors.append((runner.name, f"{type(exc).__name__}: {exc}"))

    decompositions = [d for _, d in entries]
    consensus = (
        compute_consensus(problem.id, decompositions) if decompositions else None
    )

    return CollectionResult(
        problem_id=problem.id,
        entries=tuple(entries),
        consensus=consensus,
        errors=tuple(errors),
    )


__all__ = [
    "CollectionResult",
    "artifact_to_unverified_decomposition",
    "collect",
]
