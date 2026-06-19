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

# Matches a bare Lean identifier (extraction-fallback pattern): starts with a
# letter or underscore, followed by ONE OR MORE letters, digits, underscores, or
# apostrophes. The minimum length of 2 is intentional — single-letter tokens
# ('A', 'B', 'p', 'n') are common propositional-variable names in Lean 4 and
# should NOT be treated as bare-identifier fallbacks. Real extraction-fallback
# identifiers are always longer ('lemma_3', 'h1', 'hq', 'rfl').
_LEAN_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_']+$")

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

    Known limitation — alpha-equivalence: stripping the '∀' prefix removes the
    quantifier but leaves bound variable names in the body unchanged. Two models
    writing the same step with different variable name conventions (e.g. 'k + b =
    b + k' vs 'n + m = m + n') produce disjoint token sets and score Jaccard=0.
    A fix requires extracting bound variable names from the stripped prefix and
    renaming them by first-appearance order in the body. See test_hardness.py
    test_alpha_equivalent_subgoals_reach_consensus (xfail).
    """
    stripped = _FORALL_RE.sub("", stmt.strip()).strip()
    return stripped if stripped else stmt.strip()


def _is_target_echo(stmt: str, target: str) -> bool:
    """Return True if *stmt* is an exact or normalized-exact restatement of *target*.

    Used to filter individual target-echoing subgoals from multi-subgoal
    decompositions before Jaccard computation — a model that lists the target
    itself as one of its lemmas adds no search-space signal for that subgoal.

    Unlike :func:`is_degenerate`, does NOT use token containment: short lemma
    statements legitimately share tokens with longer targets, so containment
    would produce false positives for genuine subgoals in multi-subgoal
    decompositions. Exact and normalized-exact matching is sufficient to catch
    the observed failure mode (model outputs the theorem verbatim as one of its
    claimed lemmas).
    """
    raw = stmt.strip()
    raw_target = target.strip()
    if raw == raw_target:
        return True
    return _normalize_statement(raw) == _normalize_statement(raw_target)


def _statement_set(d: Decomposition) -> frozenset[str]:
    return frozenset(
        sg.statement for sg in d.subgoals
        if not _is_target_echo(sg.statement, d.target_statement)
    )


def _normalized_statement_set(d: Decomposition) -> frozenset[str]:
    return frozenset(
        _normalize_statement(sg.statement) for sg in d.subgoals
        if not _is_target_echo(sg.statement, d.target_statement)
    )


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

    Also catches near-degenerate decompositions where the sole genuinely novel
    subgoal (after filtering target echoes) is a quantifier-weakening, trivial
    specific instance, or near-restatement of the target. When token containment
    of that sole non-echo subgoal exceeds *near_degenerate_threshold*, it carries
    no novel search-space signal. Multi-subgoal decompositions with two or more
    non-echo subgoals are never degenerate — genuine branching is present.

    Observed examples:
    - target ``∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)``
      → qwen3.5 single subgoal ``∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)`` has
      containment 1.0. (single-subgoal near-degenerate)
    - Collatz target → gemma4 produced [base-case ∃ k, iter k 1 = 1, target-echo].
      The sole non-echo (base case) has containment ~0.97 — a trivial specific
      instance that adds no decomposition signal. (sole-non-echo near-degenerate)

    Args:
        decomp: The decomposition to evaluate.
        near_degenerate_threshold: Containment fraction at or above which the sole
            non-echo subgoal is considered near-degenerate (default 0.9).
            Only evaluated when that subgoal is not already an exact match.
    """
    # Phase 0: every subgoal is a target echo → no real decomposition, regardless
    # of count. Catches ["T", "T"] the same way a single ["T"] is caught below.
    # Observed: gemma4 produced two identical target-echo subgoals on even-product.
    if decomp.subgoals and not any(
        not _is_target_echo(sg.statement, decomp.target_statement)
        for sg in decomp.subgoals
    ):
        return True
    # Multi-subgoal with at least one non-echo: cannot reliably classify as
    # degenerate using token containment alone. A genuine subgoal like "0 + n = n"
    # (commutativity of addition) shares all tokens with target "∀ n : ℕ, n + 0 = n"
    # — containment = 1.0 — yet is genuine mathematical work. Distinguishing a
    # "specific instance" (trivial, gemma4 Collatz base-case pattern) from a
    # "related theorem with shared vocabulary" requires syntactic variable-vs-constant
    # analysis not implemented here. Known limitation: multi-subgoal decompositions
    # with [near-degenerate non-echo, target-echo] escape detection. See beat 896
    # findings in analysis/legendre-vs-collatz-decomposability.md.
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


def is_confusion_non_degenerate(decomp: Decomposition) -> bool:
    """Return True when a non-degenerate output is confusion-driven, not a genuine decomposition.

    Detects two confusion patterns:

    1. **Spurious-constraint** (gpt-oss-20b pattern): a subgoal extends the target with
       extra conjuncts without decomposing it (``target ∧ k ≤ 100``,
       ``target ∧ p % 2 = 1``). The target appears as a prefix of the subgoal under
       raw, normalized-quantifier, or whitespace-collapsed comparison.

    2. **Echo-containing multi-subgoal** (gemma4 Collatz pattern): the decomposition
       has multiple subgoals, at least one of which is a target echo. The echo means
       the original problem is still present unsolved — the other subgoals are side
       steps, not genuine reductions.

    Returns False for degenerate outputs (caller should check is_degenerate first).
    """
    if is_degenerate(decomp):
        return False
    target = decomp.target_statement.strip()
    norm_target = _normalize_statement(target)
    ws_target = " ".join(target.split())

    # Pattern 1: spurious-constraint — any subgoal starts with the target plus extra.
    for sg in decomp.subgoals:
        stmt = sg.statement.strip()
        # Raw prefix check.
        if stmt != target and stmt.startswith(target):
            return True
        # Quantifier-normalized prefix check.
        norm_stmt = _normalize_statement(stmt)
        if norm_stmt != norm_target and norm_stmt.startswith(norm_target):
            return True
        # Whitespace-collapsed prefix check — catches Lean pretty-printer line-wrapped output.
        ws_stmt = " ".join(stmt.split())
        if ws_stmt != ws_target and ws_stmt.startswith(ws_target):
            return True

    # Pattern 2: echo-containing multi-subgoal — at least one subgoal is a target echo,
    # meaning the conjecture remains as an unsolved subgoal alongside side steps.
    if len(decomp.subgoals) > 1 and any(
        _is_target_echo(sg.statement, decomp.target_statement) for sg in decomp.subgoals
    ):
        return True

    return False


# Lean propositions that represent trivial tautologies — observed from gemma4-e4b-mlx
# on twin-primes (3/3 runs): the model collapses the proof to `True`, which escapes
# both is_degenerate (wrong vocabulary) and is_confusion (no target prefix).
_TRIVIAL_TAUTOLOGY_STATEMENTS: frozenset[str] = frozenset({"True", "⊤", "trivial"})


def is_trivial_tautology(decomp: Decomposition) -> bool:
    """Return True when all subgoals are trivial tautologies (e.g. ``True``).

    A decomposition that reduces the proof obligation to ``True`` or ``⊤`` is
    mathematically vacuous — it claims the theorem needs no proof. This is a
    distinct failure mode from degenerate (restatement) and confusion (spurious
    constraints): the model believes the theorem is already solved.

    Returns False for degenerate or empty decompositions.
    """
    if not decomp.subgoals or is_degenerate(decomp):
        return False
    return all(
        sg.statement.strip() in _TRIVIAL_TAUTOLOGY_STATEMENTS for sg in decomp.subgoals
    )


def _is_bare_identifier(stmt: str) -> bool:
    """Return True if *stmt* looks like a Lean identifier, not a proposition.

    Catches the extraction-fallback pattern: when the model writes a subgoal
    reference without a type annotation (e.g. ``have lemma_3 := sorry`` with
    no ``: <type>``), the collector falls back to the identifier itself as the
    statement string. A bare identifier contains no Lean operators or whitespace.

    Tautology keywords (``True``, ``⊤``, ``trivial``) are excluded — they are
    valid Lean expressions classified separately by :func:`is_trivial_tautology`.

    Examples that match: ``lemma_3``, ``h1``, ``hq``, ``rfl``.
    Examples that don't match: ``∃ p, Nat.Prime p``, ``True``, ``n + 0 = n``.
    """
    stripped = stmt.strip()
    if stripped in _TRIVIAL_TAUTOLOGY_STATEMENTS:
        return False
    return bool(_LEAN_IDENTIFIER_RE.match(stripped))


def is_reference_only(decomp: Decomposition) -> bool:
    """Return True when all subgoals are bare identifiers rather than propositions.

    Catches the extraction-fallback pattern: the model referenced lemmas by name
    (e.g. ``lemma_3``) without providing type signatures, so the extractor fell
    back to the identifier as the statement. The decomposition contributes no
    mathematical content.

    Distinct from :func:`is_trivial_tautology` (model stated a vacuously-true
    proposition like ``True``) — reference-only outputs never stated a proposition
    at all.

    Returns False for degenerate or empty decompositions.

    Observed example: gemma4-e4b-mlx on Goldbach produced sole subgoal ``lemma_3``
    across 3/3 runs (collection-goldbach-ren3-dual-v1 through v3).
    """
    if not decomp.subgoals or is_degenerate(decomp):
        return False
    return all(_is_bare_identifier(sg.statement) for sg in decomp.subgoals)


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
        n_models: Number of independent models analysed (including all excluded).
        n_degenerate: Models whose decomposition was a tautological restatement
            of the target — excluded from consensus.
        n_invalid: Models whose decomposition was non-degenerate but invalid for
            Jaccard consensus: trivial tautologies (all subgoals are ``True``/``⊤``)
            or reference-only outputs (bare identifiers without type annotations).
            Both classes produce spurious hardness inflation when paired against
            structured-correct outputs (Jaccard distance is maximised because their
            token sets share nothing with real propositions).
        n_distinct_models: Number of distinct model identifiers among the valid
            (non-degenerate, non-invalid) decompositions. ``0`` when model IDs were
            not provided to ``compute_consensus``. When ``< 2``, Jaccard is not
            computed — multiple runs of the same model produce trivially identical
            sets (hardness → 0.0 spuriously) or trivially disjoint sets if the
            model is non-deterministic (hardness → 1.0 spuriously).
        consensus_score: Mean pairwise Jaccard of valid lemma-statement sets
            (non-degenerate and non-invalid). None when fewer than 2 valid
            decompositions exist or when model IDs were provided but fewer than 2
            distinct models contributed valid results.
        hardness_score: 1 - consensus_score, or None when consensus_score is None.
        novel_statements: Every statement introduced by at least one valid model
            but not already present in any earlier valid model's submission
            (ordered by first appearance; frozenset for hashability).
    """

    problem_id: str
    n_models: int
    n_degenerate: int
    n_invalid: int
    n_distinct_models: int
    consensus_score: float | None
    hardness_score: float | None
    novel_statements: frozenset[str]


def _is_valid_for_consensus(decomp: Decomposition) -> bool:
    """Return True when a decomposition contributes genuine mathematical signal.

    A valid decomposition must be:
    - Not degenerate (restatement of the target)
    - Not a trivial tautology (all subgoals are ``True``/``⊤``)
    - Not reference-only (bare identifiers without type annotations)

    Trivial tautologies and reference-only outputs inflate hardness spuriously
    when paired against structured-correct outputs: their token sets share nothing
    with real propositions, maximising Jaccard distance regardless of whether the
    target problem is genuinely hard.
    """
    return (
        not is_degenerate(decomp)
        and not is_trivial_tautology(decomp)
        and not is_reference_only(decomp)
    )


def compute_consensus(
    problem_id: str,
    decompositions: Sequence[Decomposition],
    model_ids: Sequence[str] | None = None,
) -> ConsensusResult:
    """Compute a hardness signal from N models' decompositions of the same problem.

    *decompositions* should contain one entry per model, in the order they were
    produced (earlier = higher seniority for novelty attribution). All entries must
    share the same ``target_id``.

    *model_ids* is an optional parallel sequence of model identifier strings, one
    per decomposition. When provided, the **diversity gate** fires: if fewer than 2
    distinct model IDs appear among the valid (non-degenerate, non-invalid)
    decompositions, ``consensus_score`` and ``hardness_score`` are ``None``. Multiple
    runs of the same model produce agreement-by-construction rather than cross-model
    signal — Jaccard between identical outputs from the same model is trivially 1.0
    (hardness → 0.0 spuriously).

    Degenerate decompositions (sole subgoal == target statement) and invalid
    non-degenerate outputs (trivial tautologies, reference-only) are excluded
    before computing Jaccard consensus.

    Raises:
        ValueError: If *decompositions* is empty.
        ValueError: If *model_ids* is provided but has a different length than
            *decompositions*.
    """
    if not decompositions:
        raise ValueError("compute_consensus requires at least one decomposition")
    if model_ids is not None and len(model_ids) != len(decompositions):
        raise ValueError(
            f"model_ids length ({len(model_ids)}) must match decompositions length"
            f" ({len(decompositions)})"
        )

    n_degenerate = sum(1 for d in decompositions if is_degenerate(d))
    n_invalid = sum(
        1 for d in decompositions
        if not is_degenerate(d) and not _is_valid_for_consensus(d)
    )
    real = [d for d in decompositions if _is_valid_for_consensus(d)]

    # Diversity gate: compute distinct model IDs among valid decompositions.
    if model_ids is not None:
        n_distinct_models = len({
            mid for mid, d in zip(model_ids, decompositions)
            if _is_valid_for_consensus(d)
        })
    else:
        n_distinct_models = 0

    if not real:
        return ConsensusResult(
            problem_id=problem_id,
            n_models=len(decompositions),
            n_degenerate=n_degenerate,
            n_invalid=n_invalid,
            n_distinct_models=n_distinct_models,
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

    if len(real) < 2 or (model_ids is not None and n_distinct_models < 2):
        # Cannot compute meaningful cross-model agreement:
        # - fewer than 2 valid decompositions, OR
        # - model IDs provided but all valid decompositions are from the same model
        #   (trivially identical agreement — not a hardness signal).
        return ConsensusResult(
            problem_id=problem_id,
            n_models=len(decompositions),
            n_degenerate=n_degenerate,
            n_invalid=n_invalid,
            n_distinct_models=n_distinct_models,
            consensus_score=None,
            hardness_score=None,
            novel_statements=frozenset(novel),
        )

    consensus = pairwise_jaccard(norm_sets)

    return ConsensusResult(
        problem_id=problem_id,
        n_models=len(decompositions),
        n_degenerate=n_degenerate,
        n_invalid=n_invalid,
        n_distinct_models=n_distinct_models,
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
