"""Tests for the checker boundary that need no Lean toolchain."""

from __future__ import annotations

import pytest

from proving_ground.checker import (
    CheckerError,
    LeanInteractChecker,
    ProofArtifact,
    RecordingChecker,
    standard_axioms,
)
from proving_ground.models import Decomposition, Subgoal
from proving_ground.scoring import score_decomposition


def test_standard_axioms_allowlist():
    assert standard_axioms() == {"propext", "Classical.choice", "Quot.sound"}


def test_recording_checker_roundtrips_into_the_scorer():
    decomp = Decomposition(
        target_id="t",
        target_statement="C",
        subgoals=(Subgoal("L1", "a", discharged=True), Subgoal("L2", "b")),
        root_implication_verified=True,
        statement_matches_target=True,
        axioms_clean=True,
    )
    checker = RecordingChecker(decomp)
    artifact = ProofArtifact("t", "C", "theorem ... := by sorry", ("L1", "L2"))

    result = checker.check(artifact)
    score = score_decomposition(result)

    assert score.value == pytest.approx(0.5)
    assert score.remaining_open_ids == ("L2",)


def test_lean_interact_checker_fails_clearly_without_toolchain(monkeypatch):
    # Simulate no `lake` on PATH; construction must raise a helpful CheckerError.
    monkeypatch.setattr("proving_ground.checker.shutil.which", lambda _: None)
    with pytest.raises(CheckerError, match="No Lean toolchain"):
        LeanInteractChecker(lean_version="v4.31.0-rc1")
