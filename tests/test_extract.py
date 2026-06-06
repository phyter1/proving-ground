"""Tests for prompt construction and artifact extraction."""

from __future__ import annotations

import pytest

from proving_ground.checker import ProofArtifact
from proving_ground.extract import (
    ExtractionError,
    build_prompt,
    extract_artifact,
)
from proving_ground.models import Problem, Tier


def _problem(**kw) -> Problem:
    defaults = dict(
        id="erdos-329",
        statement="theorem target (n : ℕ) : P n := by sorry",
        tier=Tier.OPEN,
        source="formal-conjectures",
        title="A test conjecture",
        preamble="import Mathlib\nopen Nat",
    )
    defaults.update(kw)
    return Problem(**defaults)


# --- build_prompt ----------------------------------------------------------

def test_prompt_is_chat_messages_with_system_and_user():
    msgs = build_prompt(_problem())
    assert isinstance(msgs, list)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert all(set(m) == {"role", "content"} for m in msgs)


def test_prompt_contains_statement_and_preamble_verbatim():
    p = _problem()
    user = build_prompt(p)[1]["content"]
    assert p.statement in user
    assert p.preamble in user
    assert p.id in user


def test_prompt_contains_anticheat_warnings():
    user = build_prompt(_problem())[1]["content"]
    low = user.lower()
    assert "native_decide" in low
    assert "sorry" in low
    # The warning that altering the statement scores zero.
    assert "zero" in low
    # It must mention both the json manifest and the lean block.
    assert "```lean" in user
    assert "```json" in user


# --- extract_artifact: happy path -----------------------------------------

_REALISTIC_RESPONSE = """\
Sure, here is my reasoning. First a sketch:

```lean
-- draft, ignore
theorem sketch : True := trivial
```

Now the real decomposition:

```lean
import Mathlib
open Nat

lemma helper_one (n : ℕ) : Q n := by
  sorry

lemma helper_two (n : ℕ) : R n := by
  decide

theorem target (n : ℕ) : P n := by
  have := helper_one n
  have := helper_two n
  sorry
```

And the manifest:

```json
{"subgoal_ids": ["helper_one", "helper_two"]}
```

That's my submission.
"""


def test_extract_pulls_lean_and_manifest():
    p = _problem()
    art = extract_artifact(p, _REALISTIC_RESPONSE)
    assert isinstance(art, ProofArtifact)
    assert art.target_id == p.id
    assert art.target_statement == p.statement
    assert art.subgoal_ids == ("helper_one", "helper_two")
    # The LAST lean block is the real one, not the sketch.
    assert "helper_one" in art.lean_source
    assert "sketch" not in art.lean_source


def test_extract_uses_problem_as_source_of_truth_not_model():
    # Model's lean restates a tampered target, but artifact keeps the frozen spec.
    resp = """```lean\ntheorem target : True := trivial\n```\n```json\n{"subgoal_ids": []}\n```"""
    p = _problem()
    art = extract_artifact(p, resp)
    assert art.target_statement == p.statement
    assert art.target_id == p.id


# --- extract_artifact: fallback to declaration scanning -------------------

def test_extract_falls_back_to_declaration_scan_when_no_manifest():
    resp = """\
```lean
import Mathlib

lemma alpha : A := by sorry
theorem beta : B := by sorry
def gamma : C := trivial
theorem target (n : ℕ) : P n := by sorry
```
"""
    art = extract_artifact(_problem(), resp)
    # All declaration names, de-duplicated, in order.
    assert art.subgoal_ids == ("alpha", "beta", "gamma", "target")


def test_extract_falls_back_when_manifest_is_malformed_json():
    resp = """\
```lean
lemma only_lemma : X := by sorry
```
```json
{ this is not valid json
```
"""
    art = extract_artifact(_problem(), resp)
    assert art.subgoal_ids == ("only_lemma",)


def test_extract_handles_attributed_and_modified_declarations():
    resp = """\
```lean
@[simp] private lemma attr_lemma : X := by sorry
noncomputable def comp : Y := sorry
```
"""
    art = extract_artifact(_problem(), resp)
    assert art.subgoal_ids == ("attr_lemma", "comp")


# --- extract_artifact: errors ---------------------------------------------

def test_extract_raises_when_no_lean_block():
    resp = "I cannot solve this. Here is some prose with no code blocks at all."
    with pytest.raises(ExtractionError):
        extract_artifact(_problem(), resp)


def test_extract_raises_on_empty_response():
    with pytest.raises(ExtractionError):
        extract_artifact(_problem(), "   ")


def test_extract_raises_when_only_json_block_present():
    resp = """```json\n{"subgoal_ids": ["x"]}\n```"""
    with pytest.raises(ExtractionError):
        extract_artifact(_problem(), resp)


def test_extract_untagged_block_treated_as_lean():
    # No language tag on the fence — should be taken as the lean source.
    resp = """\
```
lemma untagged : X := by sorry
```
"""
    art = extract_artifact(_problem(), resp)
    assert "untagged" in art.lean_source
    assert art.subgoal_ids == ("untagged",)
