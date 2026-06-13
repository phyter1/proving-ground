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

import re
from dataclasses import dataclass
from typing import Sequence

from proving_ground.models import Decomposition

# Matches one or more leading '∀ <vars> : <type>, ' blocks.
# Stripping these lets '∀ n : ℕ, n + 0 = n' and 'n + 0 = n' compare as identical —
# a model that echoes the target with quantifiers stripped has still not decomposed anything.
_FORALL_RE = re.compile(r"^(?:∀\s+[^,]+,\s*)+")


def _normalize_statement(stmt: str) -> str:
    """Strip leading universal quantifier prefixes for semantic comparison.

    Lean statements surface the same proposition with or without explicit '∀'
    wrappers. Without normalization, token-Jaccard marks models that agree
    semantically as disagreeing — inflating hardness_score spuriously on
    calibration problems where every model reaches the same answer.

    Only strips leading '∀' blocks; '∃' and body-level quantifiers are preserved.
    Returns the original string if stripping would produce an empty result.
    """
    stripped = _FORALL_RE.sub("", stmt.strip()).strip()
    return stripped if stripped else stmt.strip()


def _statement_set(d: Decomposition) -> frozenset[str]:
    return frozenset(sg.statement for sg in d.subgoals)


def _normalized_statement_set(d: Decomposition) -> frozenset[str]:
    return frozenset(_normalize_statement(sg.statement) for sg in d.subgoals)


def _token_containment(subgoal_stmt: str, target_stmt: str) -> float:
    """Fraction of the subgoal's whitespace-delimited tokens that appear in the target.

    A near-degenerate rephrasing (e.g. dropping a universal quantifier to get a
    weaker existential sub-claim) will have nearly all of its tokens present in
    the full target statement because it is derived from the same vocabulary.
    A genuine decomposition step introduces new lemma names, bound variables, or
    intermediate concepts that are not in the target.
    """
    sub_tokens = frozenset(subgoal_stmt.split())
    tgt_tokens = frozenset(target_stmt.split())
    if not sub_tokens:
        return 1.0
    return len(sub_tokens & tgt_tokens) / len(sub_tokens)


def is_degenerate(decomp: Decomposition, near_degenerate_threshold: float = 0.9) -> bool:
    """Return True if the decomposition is a tautological or near-tautological non-decomposition.

    A model that outputs the theorem statement itself as its sole subgoal has
    not decomposed anything — Jaccard against any real decomposition is always
    0, inflating hardness_score spuriously. Filter these before computing
    consensus.

    Also catches near-degenerate single-subgoal decompositions: a subgoal that
    is a quantifier-weakening or rearrangement of the target uses almost
    exclusively tokens already present in the target. When token containment
    (fraction of subgoal tokens found in the target) exceeds
    *near_degenerate_threshold*, the subgoal carries no novel search-space
    signal and is filtered the same way as an exact echo.

    Observed example: target ``∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)``
    → qwen3.5 subgoal ``∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)`` has containment 1.0.

    Args:
        decomp: The decomposition to evaluate.
        near_degenerate_threshold: Containment fraction at or above which a
            single-subgoal decomposition is considered near-degenerate (default 0.9).
            Only evaluated when the subgoal is not already an exact match.
    """
    if len(decomp.subgoals) != 1:
        return False
    raw_stmt = decomp.subgoals[0].statement.strip()
    raw_target = decomp.target_statement.strip()
    # Phase 1: exact match on raw strings.
    if raw_stmt == raw_target:
        return True
    # Phase 2: normalized exact match — catches models that echo the theorem
    # after dropping leading ∀ wrappers (e.g. 'n + 0 = n' vs '∀ n : ℕ, n + 0 = n').
    if _normalize_statement(raw_stmt) == _normalize_statement(raw_target):
        return True
    # Phase 3: near-degenerate token containment — uses RAW strings intentionally.
    # Normalizing before containment produces false positives: a short normalized
    # form (e.g. 'Q n' from '∀ n, Q n') appears coincidentally inside a longer
    # normalized target ('P n → Q n') even when they are genuinely distinct claims.
    return _token_containment(raw_stmt, raw_target) >= near_degenerate_threshold


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

    # Raw sets for novel-statement attribution (preserve display strings).
    raw_sets = [_statement_set(d) for d in real]
    # Normalized sets for Jaccard consensus (semantic deduplication across models).
    norm_sets = [_normalized_statement_set(d) for d in real]

    seen: set[str] = set()
    novel: set[str] = set()
    for stmt_set in raw_sets:
        novel.update(stmt_set - seen)
        seen.update(stmt_set)

    if len(real) < 2:
        # Cannot compute cross-model agreement with a single real decomposition.
        # Return None rather than the pairwise_jaccard default of 1.0 (which
        # would imply "trivially tractable" — a false signal when only one model
        # produced a non-degenerate result).
        return ConsensusResult(
            problem_id=problem_id,
            n_models=len(decompositions),
            n_degenerate=n_degenerate,
            consensus_score=None,
            hardness_score=None,
            novel_statements=frozenset(novel),
        )

    consensus = pairwise_jaccard(norm_sets)

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
