"""Cross-model agreement as a hardness proxy for the benchmark metric.

When N independent models decompose the same open problem, high pairwise Jaccard
similarity of their lemma-statement sets suggests the decomposition path was obvious
(low hardness). High disagreement suggests genuine search-space branching (high hardness).

This module is pure and dependency-free — same design principle as scoring.py. It
operates on Decomposition objects and returns a ConsensusResult; callers decide whether
to use the novelty weights as a multiplier on the existing auto-closable metric.

Relation to scoring.py: the auto-closable discount is a *floor* (don't credit trivial
lemmas). The novelty weight here is a *ceiling complement* (credit harder, novel lemmas
more). Together: lemma_score = novelty_weight(statement) × (1 - auto_closable_flag).

Reference design note: notes/archive/proving-ground-hardness-signal.md (2026-06-12).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from proving_ground.models import Decomposition


def _statement_set(d: Decomposition) -> frozenset[str]:
    return frozenset(sg.statement for sg in d.subgoals)


def is_degenerate(decomp: Decomposition) -> bool:
    """Return True if the decomposition is a tautological non-decomposition.

    A model that outputs the theorem statement itself as its sole subgoal has
    not decomposed anything — Jaccard against any real decomposition is always
    0, inflating hardness_score spuriously. Filter these before computing
    consensus.

    The check is string equality after stripping whitespace. Structural
    equivalence (alpha-renaming, notation unfolding) is out of scope for now.
    """
    if len(decomp.subgoals) != 1:
        return False
    return decomp.subgoals[0].statement.strip() == decomp.target_statement.strip()


def pairwise_jaccard(sets: Sequence[frozenset[str]]) -> float:
    """Mean pairwise Jaccard similarity across all pairs in *sets*.

    Returns 1.0 when fewer than 2 sets are provided (trivially identical).
    Returns 1.0 when both members of a pair are empty (identical by convention).
    """
    if len(sets) < 2:
        return 1.0
    total, count = 0.0, 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            union = a | b
            total += 1.0 if not union else len(a & b) / len(union)
            count += 1
    return total / count


@dataclass(frozen=True)
class ConsensusResult:
    """Cross-model consensus analysis for a single problem.

    Attributes:
        problem_id: The problem all decompositions address.
        n_models: Number of independent models analysed (including degenerate).
        n_degenerate: Models whose sole subgoal was the theorem statement itself
            (tautological non-decompositions, excluded from consensus computation).
        consensus_score: Mean pairwise Jaccard of non-degenerate lemma-statement
            sets. None when every model produced a degenerate decomposition —
            the signal is undefined, not zero hardness.
        hardness_score: 1 - consensus_score, or None when consensus_score is None.
        novel_statements: Every statement introduced by at least one non-degenerate
            model but not already present in any earlier model's submission
            (ordered by first appearance; frozenset for hashability).
    """

    problem_id: str
    n_models: int
    n_degenerate: int
    consensus_score: float | None
    hardness_score: float | None
    novel_statements: frozenset[str]


def compute_consensus(
    problem_id: str,
    decompositions: Sequence[Decomposition],
) -> ConsensusResult:
    """Compute a hardness signal from N models' decompositions of the same problem.

    *decompositions* should contain one entry per model, in the order they were
    produced (earlier = higher seniority for novelty attribution). All entries must
    share the same ``target_id``.

    Degenerate decompositions (sole subgoal == target statement) are excluded
    before computing Jaccard consensus; if all decompositions are degenerate,
    ``consensus_score`` and ``hardness_score`` are ``None``.

    Raises:
        ValueError: If *decompositions* is empty.
    """
    if not decompositions:
        raise ValueError("compute_consensus requires at least one decomposition")

    n_degenerate = sum(1 for d in decompositions if is_degenerate(d))
    real = [d for d in decompositions if not is_degenerate(d)]

    if not real:
        return ConsensusResult(
            problem_id=problem_id,
            n_models=len(decompositions),
            n_degenerate=n_degenerate,
            consensus_score=None,
            hardness_score=None,
            novel_statements=frozenset(),
        )

    all_sets = [_statement_set(d) for d in real]
    consensus = pairwise_jaccard(all_sets)

    seen: set[str] = set()
    novel: set[str] = set()
    for stmt_set in all_sets:
        novel.update(stmt_set - seen)
        seen.update(stmt_set)

    return ConsensusResult(
        problem_id=problem_id,
        n_models=len(decompositions),
        n_degenerate=n_degenerate,
        consensus_score=consensus,
        hardness_score=1.0 - consensus,
        novel_statements=frozenset(novel),
    )


def novelty_weight(statement: str, seen_before: frozenset[str], hardness_score: float) -> float:
    """Novelty weight for a single lemma statement in a cross-model run.

    A statement seen in no prior model's submission earns full hardness-scaled
    weight. A repeated statement earns zero — it was an obvious step.

    This is intended as a *multiplier* on a per-lemma basis, not a problem-level
    scalar. Combine with the auto-closable discount from scoring.py:

        per_lemma_credit = novelty_weight(stmt, seen, hardness) × (1 - auto_closable)

    Args:
        statement: The Lean statement of the lemma being scored.
        seen_before: Statements proposed by all *earlier* model submissions.
        hardness_score: The ConsensusResult.hardness_score for this problem.

    Returns:
        0.0 if *statement* is in *seen_before*; *hardness_score* otherwise.
    """
    return 0.0 if statement in seen_before else hardness_score
