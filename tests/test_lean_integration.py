"""Integration tests against a LIVE Lean kernel.

Skipped automatically where there is no toolchain (CI, dev laptops). Runs on the fleet
(ren4) with elan on PATH, the project at $PG_LEAN_PROJECT, and lean-interact installed.
This is the test that proves the verification leaves actually work against real Lean.
"""

from __future__ import annotations

import os
import shutil

import pytest

from proving_ground.checker import LeanInteractChecker, ProofArtifact
from proving_ground.scoring import ScoreKind, score_decomposition

pytestmark = pytest.mark.skipif(
    shutil.which("lake") is None, reason="no Lean toolchain (lake) on PATH"
)

PROJECT_DIR = os.environ.get("PG_LEAN_PROJECT", "/models/proving-ground-lean")

TARGET = "((1 : Nat) + 0 = 1) ∧ ((0 : Nat) + 1 = 1)"


@pytest.fixture(scope="module")
def checker():
    return LeanInteractChecker(project_dir=PROJECT_DIR)


def _artifact(source: str, target: str = TARGET, root: str = "reduction") -> ProofArtifact:
    return ProofArtifact(
        target_id="it-1",
        target_statement=target,
        lean_source=source,
        subgoal_ids=("sg_a", "sg_b"),
        root_name=root,
    )


def test_partial_reduction_scores_half(checker):
    # sg_a proven, sg_b left open, reduction valid and concludes the frozen target.
    source = """\
theorem sg_a : (1 : Nat) + 0 = 1 := by simp
theorem sg_b : (0 : Nat) + 1 = 1 := by sorry
theorem reduction :
    ((1 : Nat) + 0 = 1) → ((0 : Nat) + 1 = 1) →
    (((1 : Nat) + 0 = 1) ∧ ((0 : Nat) + 1 = 1)) :=
  fun h1 h2 => ⟨h1, h2⟩
"""
    decomp = checker.check(_artifact(source))
    score = score_decomposition(decomp)
    assert score.kind is ScoreKind.REDUCTION
    assert score.value == pytest.approx(0.5)
    assert score.remaining_open_ids == ("sg_b",)


def test_full_proof_scores_one(checker):
    source = """\
theorem sg_a : (1 : Nat) + 0 = 1 := by simp
theorem sg_b : (0 : Nat) + 1 = 1 := by simp
theorem reduction :
    ((1 : Nat) + 0 = 1) → ((0 : Nat) + 1 = 1) →
    (((1 : Nat) + 0 = 1) ∧ ((0 : Nat) + 1 = 1)) :=
  fun h1 h2 => ⟨h1, h2⟩
"""
    score = score_decomposition(checker.check(_artifact(source)))
    assert score.kind is ScoreKind.SOLVED
    assert score.value == pytest.approx(1.0)


def test_goal_tampering_scores_zero(checker):
    # reduction concludes `True`, not the frozen target -> statement integrity fails.
    source = """\
theorem sg_a : (1 : Nat) + 0 = 1 := by simp
theorem sg_b : (0 : Nat) + 1 = 1 := by simp
theorem reduction : ((1 : Nat) + 0 = 1) → ((0 : Nat) + 1 = 1) → True :=
  fun _ _ => trivial
"""
    score = score_decomposition(checker.check(_artifact(source)))
    assert score.value == 0.0
    assert score.kind is ScoreKind.NONE


def test_sorry_in_reduction_scores_zero(checker):
    # The reduction itself is faked with sorry -> sorryAx -> not clean.
    source = """\
theorem sg_a : (1 : Nat) + 0 = 1 := by simp
theorem sg_b : (0 : Nat) + 1 = 1 := by simp
theorem reduction :
    ((1 : Nat) + 0 = 1) → ((0 : Nat) + 1 = 1) →
    (((1 : Nat) + 0 = 1) ∧ ((0 : Nat) + 1 = 1)) := by sorry
"""
    score = score_decomposition(checker.check(_artifact(source)))
    assert score.value == 0.0
