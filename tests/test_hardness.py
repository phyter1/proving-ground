"""Tests for the cross-model agreement / hardness signal module."""

from __future__ import annotations

import pytest

from proving_ground.hardness import (
    ConsensusResult,
    compute_consensus,
    novelty_weight,
    pairwise_jaccard,
)
from proving_ground.models import Decomposition, Subgoal


# --- helpers ----------------------------------------------------------------


def _decomp(target_id: str, statements: list[str]) -> Decomposition:
    """Minimal Decomposition passing all hard gates."""
    return Decomposition(
        target_id=target_id,
        target_statement="C",
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


# --- compute_consensus ------------------------------------------------------


def test_identical_decompositions_zero_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "B"])
    r = compute_consensus("conj-1", [d1, d2])
    assert isinstance(r, ConsensusResult)
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert r.n_models == 2
    assert r.problem_id == "conj-1"


def test_disjoint_decompositions_full_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["C", "D"])
    r = compute_consensus("conj-1", [d1, d2])
    assert r.hardness_score == pytest.approx(1.0)


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


def test_three_model_partial_overlap():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "C"])
    d3 = _decomp("conj-1", ["D", "E"])
    # pairs: (d1,d2): |{A}|/|{A,B,C}|=1/3, (d1,d3): 0/4=0, (d2,d3): 0/4=0
    # mean = (1/3 + 0 + 0) / 3 = 1/9
    r = compute_consensus("conj-1", [d1, d2, d3])
    assert r.consensus_score == pytest.approx(1 / 9)
    assert r.hardness_score == pytest.approx(8 / 9)


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
