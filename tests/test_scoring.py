"""Acceptance tests for the partial-credit metric — the core IP.

These encode docs/SCORING.md as executable spec. Written before the implementation.
"""

from __future__ import annotations

import pytest

from proving_ground import (
    Decomposition,
    ScoreKind,
    Subgoal,
    score_decomposition,
)


# --- helpers ---------------------------------------------------------------

def _clean(subgoals, *, root=True, matches=True, axioms=True, target="C"):
    """A decomposition that passes all hard gates by default."""
    return Decomposition(
        target_id="conj-1",
        target_statement=target,
        subgoals=tuple(subgoals),
        root_implication_verified=root,
        statement_matches_target=matches,
        axioms_clean=axioms,
    )


# --- full solve ------------------------------------------------------------

def test_all_subgoals_discharged_scores_one():
    d = _clean([
        Subgoal("L1", "lemma1", discharged=True),
        Subgoal("L2", "lemma2", discharged=True),
    ])
    s = score_decomposition(d)
    assert s.value == 1.0
    assert s.kind is ScoreKind.SOLVED
    assert s.remaining_open_ids == ()


def test_direct_proof_no_subgoals_scores_one():
    # A direct proof = a verified reduction with an empty subgoal set.
    d = _clean([])
    s = score_decomposition(d)
    assert s.value == 1.0
    assert s.kind is ScoreKind.SOLVED


# --- partial credit --------------------------------------------------------

def test_half_discharged_scores_half():
    d = _clean([
        Subgoal("L1", "lemma1", discharged=True),
        Subgoal("L2", "lemma2", discharged=False),
    ])
    s = score_decomposition(d)
    assert s.value == pytest.approx(0.5)
    assert s.kind is ScoreKind.REDUCTION
    assert s.remaining_open_ids == ("L2",)


def test_weighted_partial_credit():
    d = _clean([
        Subgoal("L1", "easy", weight=1.0, discharged=True),
        Subgoal("L2", "hard", weight=3.0, discharged=False),
    ])
    s = score_decomposition(d)
    assert s.value == pytest.approx(0.25)  # 1 / (1+3)
    assert s.kind is ScoreKind.REDUCTION


def test_pure_reduction_nothing_discharged_scores_zero_but_surfaces_lemmas():
    # A verified reduction with nothing proven: scalar 0 in v1, but the new open
    # lemmas must still be surfaced — they are the self-renewing engine.
    d = _clean([
        Subgoal("L1", "newlemma1", discharged=False),
        Subgoal("L2", "newlemma2", discharged=False),
    ])
    s = score_decomposition(d)
    assert s.value == 0.0
    assert s.kind is ScoreKind.REDUCTION
    assert set(s.remaining_open_ids) == {"L1", "L2"}


# --- hard gates (any failure => 0.0, kind NONE) ----------------------------

def test_statement_tampering_scores_zero():
    d = _clean([Subgoal("L1", "lemma1", discharged=True)], matches=False)
    s = score_decomposition(d)
    assert s.value == 0.0
    assert s.kind is ScoreKind.NONE
    assert "statement" in s.rationale.lower()


def test_dirty_axioms_score_zero():
    d = _clean([Subgoal("L1", "lemma1", discharged=True)], axioms=False)
    s = score_decomposition(d)
    assert s.value == 0.0
    assert s.kind is ScoreKind.NONE
    assert "axiom" in s.rationale.lower()


def test_unverified_root_implication_scores_zero():
    # Even with discharged subgoals, no verified (subgoals -> target) = sorry relocation.
    d = _clean([Subgoal("L1", "lemma1", discharged=True)], root=False)
    s = score_decomposition(d)
    assert s.value == 0.0
    assert s.kind is ScoreKind.NONE
    assert "implication" in s.rationale.lower()


def test_trivial_identity_reduction_scores_zero():
    # "C follows from C" — a remaining open subgoal equal to the target.
    d = _clean(
        [Subgoal("L1", "C", discharged=False)],  # statement == target_statement
        target="C",
    )
    s = score_decomposition(d)
    assert s.value == 0.0
    assert s.kind is ScoreKind.NONE
    assert "trivial" in s.rationale.lower() or "identity" in s.rationale.lower()


def test_trivial_identity_allowed_if_that_subgoal_is_discharged():
    # If the subgoal equal to the target is actually proven, it's a real proof, not a
    # null reduction. (Edge case: the "decomposition" is just proving C directly.)
    d = _clean([Subgoal("L1", "C", discharged=True)], target="C")
    s = score_decomposition(d)
    assert s.value == 1.0
    assert s.kind is ScoreKind.SOLVED


# --- robustness ------------------------------------------------------------

def test_score_value_always_in_unit_interval():
    d = _clean([
        Subgoal("L1", "a", weight=2.0, discharged=True),
        Subgoal("L2", "b", weight=5.0, discharged=False),
        Subgoal("L3", "c", weight=0.0, discharged=False),
    ])
    s = score_decomposition(d)
    assert 0.0 <= s.value <= 1.0


def test_negative_weight_rejected_at_construction():
    with pytest.raises(ValueError):
        Subgoal("bad", "x", weight=-1.0)
