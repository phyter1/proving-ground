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
        n_models: Number of independent models analysed.
        consensus_score: Mean pairwise Jaccard of lemma-statement sets.
            0.0 = total disagreement, 1.0 = all models identical.
        hardness_score: 1 - consensus_score.
        novel_statements: Every statement introduced by at least one model but
            not already present in any earlier model's submission (ordered by
            first appearance; frozenset for hashability).
    """

    problem_id: str
    n_models: int
    consensus_score: float
    hardness_score: float
    novel_statements: frozenset[str]


def compute_consensus(
    problem_id: str,
    decompositions: Sequence[Decomposition],
) -> ConsensusResult:
    """Compute a hardness signal from N models' decompositions of the same problem.

    *decompositions* should contain one entry per model, in the order they were
    produced (earlier = higher seniority for novelty attribution). All entries must
    share the same ``target_id``.

    Raises:
        ValueError: If *decompositions* is empty.
    """
    if not decompositions:
        raise ValueError("compute_consensus requires at least one decomposition")

    all_sets = [_statement_set(d) for d in decompositions]
    consensus = pairwise_jaccard(all_sets)

    seen: set[str] = set()
    novel: set[str] = set()
    for stmt_set in all_sets:
        novel.update(stmt_set - seen)
        seen.update(stmt_set)

    return ConsensusResult(
        problem_id=problem_id,
        n_models=len(decompositions),
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
