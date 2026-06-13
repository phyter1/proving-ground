"""Tests for the cross-model agreement / hardness signal module."""

from __future__ import annotations

import pytest

from proving_ground.hardness import (
    ConsensusResult,
    compute_consensus,
    is_degenerate,
    novelty_weight,
    pairwise_jaccard,
)
from proving_ground.models import Decomposition, Subgoal

THEOREM = "∀ n : ℕ, Even n ∨ Odd n"


# --- helpers ----------------------------------------------------------------


def _decomp(target_id: str, statements: list[str], target_statement: str = "C") -> Decomposition:
    """Minimal Decomposition passing all hard gates."""
    return Decomposition(
        target_id=target_id,
        target_statement=target_statement,
        subgoals=tuple(Subgoal(f"L{i}", s) for i, s in enumerate(statements)),
        root_implication_verified=True,
        statement_matches_target=True,
        axioms_clean=True,
    )


# --- pairwise_jaccard -------------------------------------------------------


def test_identical_sets_returns_one():
    s = frozenset({"A", "B"})
    assert pairwise_jaccard([s, s, s]) == pytest.approx(1.0)


def test_disjoint_sets_returns_zero():
    a = frozenset({"A", "B"})
    b = frozenset({"C", "D"})
    assert pairwise_jaccard([a, b]) == pytest.approx(0.0)


def test_partial_overlap_two_sets():
    a = frozenset({"A", "B"})
    b = frozenset({"A", "C"})
    # intersection = {A}, union = {A, B, C}, jaccard = 1/3
    assert pairwise_jaccard([a, b]) == pytest.approx(1 / 3)


def test_single_set_returns_one():
    assert pairwise_jaccard([frozenset({"A", "B"})]) == pytest.approx(1.0)


def test_empty_list_returns_one():
    assert pairwise_jaccard([]) == pytest.approx(1.0)


def test_both_empty_sets_return_one():
    assert pairwise_jaccard([frozenset(), frozenset()]) == pytest.approx(1.0)


def test_three_sets_mean_of_three_pairs():
    a = frozenset({"A"})
    b = frozenset({"B"})
    c = frozenset({"A"})
    # pairs: (a,b)=0, (a,c)=1, (b,c)=0 → mean = 1/3
    assert pairwise_jaccard([a, b, c]) == pytest.approx(1 / 3)


def test_one_empty_one_nonempty():
    a = frozenset()
    b = frozenset({"A"})
    # union = {A}, intersection = {} → 0
    assert pairwise_jaccard([a, b]) == pytest.approx(0.0)


# --- is_degenerate ----------------------------------------------------------


def test_sole_subgoal_equals_target_is_degenerate():
    d = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    assert is_degenerate(d) is True


def test_sole_subgoal_equals_target_with_whitespace_is_degenerate():
    d = _decomp("conj-1", [f"  {THEOREM}  "], target_statement=THEOREM)
    assert is_degenerate(d) is True


def test_sole_subgoal_differs_is_not_degenerate():
    d = _decomp("conj-1", ["Even 0 ∨ Odd 0"], target_statement=THEOREM)
    assert is_degenerate(d) is False


def test_multiple_subgoals_not_degenerate_even_if_one_matches():
    # Two subgoals: not a degenerate echo regardless of content
    d = _decomp("conj-1", [THEOREM, "Even 0 ∨ Odd 0"], target_statement=THEOREM)
    assert is_degenerate(d) is False


def test_empty_subgoals_not_degenerate():
    d = _decomp("conj-1", [], target_statement=THEOREM)
    assert is_degenerate(d) is False


# --- compute_consensus ------------------------------------------------------


def test_identical_decompositions_zero_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "B"])
    r = compute_consensus("conj-1", [d1, d2])
    assert isinstance(r, ConsensusResult)
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert r.n_models == 2
    assert r.n_degenerate == 0
    assert r.problem_id == "conj-1"


def test_disjoint_decompositions_full_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["C", "D"])
    r = compute_consensus("conj-1", [d1, d2])
    assert r.hardness_score == pytest.approx(1.0)
    assert r.n_degenerate == 0


def test_novel_statements_first_model_all_novel():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "C"])
    r = compute_consensus("conj-1", [d1, d2])
    # A is in d1 first, B is in d1, C is in d2 but not d1
    assert {"A", "B", "C"} == r.novel_statements


def test_single_decomposition_hardness_zero():
    # Only one model: pairwise_jaccard returns 1.0 → hardness 0.0
    d = _decomp("conj-1", ["A", "B"])
    r = compute_consensus("conj-1", [d])
    assert r.hardness_score == pytest.approx(0.0)
    assert r.n_models == 1
    assert r.n_degenerate == 0


def test_empty_decompositions_raises():
    with pytest.raises(ValueError):
        compute_consensus("conj-1", [])


def test_empty_subgoal_sets_high_consensus():
    # Both models produced no lemmas — trivially identical
    d1 = _decomp("conj-1", [])
    d2 = _decomp("conj-1", [])
    r = compute_consensus("conj-1", [d1, d2])
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert r.novel_statements == frozenset()
    assert r.n_degenerate == 0


def test_three_model_partial_overlap():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "C"])
    d3 = _decomp("conj-1", ["D", "E"])
    # pairs: (d1,d2): |{A}|/|{A,B,C}|=1/3, (d1,d3): 0/4=0, (d2,d3): 0/4=0
    # mean = (1/3 + 0 + 0) / 3 = 1/9
    r = compute_consensus("conj-1", [d1, d2, d3])
    assert r.consensus_score == pytest.approx(1 / 9)
    assert r.hardness_score == pytest.approx(8 / 9)
    assert r.n_degenerate == 0


def test_all_degenerate_consensus_is_none():
    # Reproduces the beat 655 failure: Qwen3.5 echoed the theorem statement
    d1 = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    d2 = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    r = compute_consensus("conj-1", [d1, d2])
    assert r.consensus_score is None
    assert r.hardness_score is None
    assert r.n_models == 2
    assert r.n_degenerate == 2
    assert r.novel_statements == frozenset()


def test_mixed_degenerate_computes_on_real_only():
    # One degenerate (Qwen3.5-style echo), one real (Gemma4-style inductive decomp)
    echo = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    real = _decomp("conj-1", ["Even 0 ∨ Odd 0", "Even (S k) ∨ Odd (S k)"], target_statement=THEOREM)
    r = compute_consensus("conj-1", [echo, real])
    # Only one non-degenerate model: pairwise_jaccard([set]) = 1.0 → hardness 0.0
    assert r.n_models == 2
    assert r.n_degenerate == 1
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert "Even 0 ∨ Odd 0" in r.novel_statements
    assert "Even (S k) ∨ Odd (S k)" in r.novel_statements


def test_mixed_degenerate_two_real_models_computes_correctly():
    # Degenerate + two real models with partial overlap
    echo = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    d1 = _decomp("conj-1", ["A", "B"], target_statement=THEOREM)
    d2 = _decomp("conj-1", ["A", "C"], target_statement=THEOREM)
    r = compute_consensus("conj-1", [echo, d1, d2])
    assert r.n_models == 3
    assert r.n_degenerate == 1
    # pairwise_jaccard([{A,B},{A,C}]) = 1/3
    assert r.consensus_score == pytest.approx(1 / 3)
    assert r.hardness_score == pytest.approx(2 / 3)


# --- novelty_weight ---------------------------------------------------------


def test_seen_statement_zero_weight():
    seen = frozenset({"A", "B"})
    assert novelty_weight("A", seen, hardness_score=0.8) == pytest.approx(0.0)
    assert novelty_weight("B", seen, hardness_score=0.5) == pytest.approx(0.0)


def test_novel_statement_scaled_by_hardness():
    seen = frozenset({"A"})
    assert novelty_weight("C", seen, hardness_score=0.7) == pytest.approx(0.7)
    assert novelty_weight("D", seen, hardness_score=1.0) == pytest.approx(1.0)


def test_novel_statement_zero_hardness_zero_weight():
    # Trivially obvious problem (all models agreed) → new lemma still earns 0
    seen = frozenset()
    assert novelty_weight("A", seen, hardness_score=0.0) == pytest.approx(0.0)


def test_empty_seen_any_statement_novel():
    assert novelty_weight("X", frozenset(), hardness_score=0.6) == pytest.approx(0.6)
