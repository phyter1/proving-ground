"""Tests for the multi-model collection harness — network-free via fakes."""

from __future__ import annotations

import json

import httpx
import pytest

from proving_ground.checker import ProofArtifact
from proving_ground.collector import (
    CollectionResult,
    _extract_type_from_sig,
    _statements_from_artifact,
    artifact_to_unverified_decomposition,
    collect,
)
from proving_ground.models import Problem, Tier
from proving_ground.runner import OpenAICompatibleRunner


# --- helpers ----------------------------------------------------------------


def _problem(**kw) -> Problem:
    defaults = dict(
        id="test-conjecture-1",
        statement="∀ n : ℕ, P n → Q n",
        tier=Tier.WEAKLY_OPEN,
        source="test",
        preamble="import Mathlib",
    )
    defaults.update(kw)
    return Problem(**defaults)


def _lean_source(*lemmas: tuple[str, str]) -> str:
    """Build minimal Lean source with the given (name, type) lemma pairs."""
    lines = ["import Mathlib", ""]
    for name, ty in lemmas:
        lines.append(f"theorem {name} : {ty} := by sorry")
    lines += [
        "",
        "theorem reduction (h1 : L1_type) : ∀ n : ℕ, P n → Q n := by exact h1",
        "",
    ]
    return "\n".join(lines)


def _artifact(
    subgoal_ids: list[str],
    lean_source: str,
    *,
    target_id: str = "test-conjecture-1",
    target_statement: str = "∀ n : ℕ, P n → Q n",
) -> ProofArtifact:
    return ProofArtifact(
        target_id=target_id,
        target_statement=target_statement,
        lean_source=lean_source,
        subgoal_ids=tuple(subgoal_ids),
        root_name="reduction",
    )


def _chat_response(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def _model_response(lemmas: list[tuple[str, str]], target: str = "∀ n : ℕ, P n → Q n") -> str:
    """Build a well-formed model response matching the extract_artifact protocol."""
    lean = _lean_source(*lemmas)
    ids = json.dumps({"subgoal_ids": [n for n, _ in lemmas], "root_name": "reduction"})
    return f"```lean\n{lean}\n```\n\n```json\n{ids}\n```"


# --- _extract_type_from_sig -------------------------------------------------


def test_extract_simple_type():
    sig = " (n : ℕ) : P n → Q n"
    assert _extract_type_from_sig(sig) == "P n → Q n"


def test_extract_no_colon_returns_sig():
    sig = " (n : ℕ)"
    # Depth-0 colon is inside parens; falls through to returning stripped sig.
    assert _extract_type_from_sig(sig) == "(n : ℕ)"


def test_extract_nested_brackets_skipped():
    sig = " (f : α → β) : ∀ x, f x = f x"
    assert _extract_type_from_sig(sig) == "∀ x, f x = f x"


def test_extract_empty_sig():
    assert _extract_type_from_sig("") == ""


# --- _statements_from_artifact ----------------------------------------------


def test_statements_extracted_for_all_subgoals():
    source = _lean_source(("base_case", "P 0 → Q 0"), ("inductive_step", "∀ n, P n → Q n"))
    art = _artifact(["base_case", "inductive_step"], source)
    stmts = _statements_from_artifact(art)
    assert stmts["base_case"] == "P 0 → Q 0"
    assert stmts["inductive_step"] == "∀ n, P n → Q n"


def test_missing_declaration_falls_back_to_id():
    source = _lean_source(("base_case", "P 0 → Q 0"))
    art = _artifact(["base_case", "ghost_lemma"], source)
    stmts = _statements_from_artifact(art)
    assert stmts["base_case"] == "P 0 → Q 0"
    assert stmts["ghost_lemma"] == "ghost_lemma"  # fallback


def test_empty_subgoal_ids_returns_empty():
    source = _lean_source(("L1", "P 0"))
    art = _artifact([], source)
    assert _statements_from_artifact(art) == {}


# --- artifact_to_unverified_decomposition -----------------------------------


def test_all_flags_false():
    source = _lean_source(("L1", "P 0 → Q 0"))
    art = _artifact(["L1"], source)
    decomp = artifact_to_unverified_decomposition(art)
    assert not decomp.root_implication_verified
    assert not decomp.statement_matches_target
    assert not decomp.axioms_clean


def test_subgoal_statements_populated():
    source = _lean_source(("L1", "P 0 → Q 0"), ("L2", "P 1 → Q 1"))
    art = _artifact(["L1", "L2"], source)
    decomp = artifact_to_unverified_decomposition(art)
    stmts = {sg.statement for sg in decomp.subgoals}
    assert "P 0 → Q 0" in stmts
    assert "P 1 → Q 1" in stmts


def test_no_subgoals():
    source = "import Mathlib\ntheorem reduction : ∀ n : ℕ, P n → Q n := by sorry"
    art = _artifact([], source)
    decomp = artifact_to_unverified_decomposition(art)
    assert decomp.subgoals == ()


def test_target_fields_preserved():
    source = _lean_source(("L1", "P 0"))
    art = _artifact(["L1"], source, target_id="my-problem", target_statement="P 0")
    decomp = artifact_to_unverified_decomposition(art)
    assert decomp.target_id == "my-problem"
    assert decomp.target_statement == "P 0"


# --- collect ----------------------------------------------------------------


class FakeRunner:
    """Returns a fixed canned response without any network call."""

    def __init__(self, name: str, response: str) -> None:
        self.name = name
        self._response = response

    def complete(self, messages):
        return self._response


class FailingRunner:
    """Always raises RunnerError."""

    name = "failing-runner"

    def complete(self, messages):
        from proving_ground.runner import RunnerError

        raise RunnerError("endpoint unreachable")


def test_collect_two_models_returns_consensus():
    prob = _problem()
    r1 = FakeRunner("model-a", _model_response([("L1", "P 0 → Q 0"), ("L2", "∀ n, P n")]))
    r2 = FakeRunner("model-b", _model_response([("L1", "P 0 → Q 0"), ("L3", "∀ n, Q n")]))
    result = collect(prob, [r1, r2])
    assert result.problem_id == "test-conjecture-1"
    assert len(result.entries) == 2
    assert result.consensus is not None
    assert result.errors == ()
    # L1 shared → some overlap → consensus > 0
    assert result.consensus.consensus_score > 0.0


def test_collect_identical_models_consensus_one():
    prob = _problem()
    response = _model_response([("L1", "P 0 → Q 0"), ("L2", "∀ n, P n")])
    r1 = FakeRunner("model-a", response)
    r2 = FakeRunner("model-b", response)
    result = collect(prob, [r1, r2])
    assert result.consensus is not None
    assert result.consensus.consensus_score == pytest.approx(1.0)


def test_collect_disjoint_models_consensus_zero():
    prob = _problem()
    r1 = FakeRunner("model-a", _model_response([("L1", "P 0 → Q 0")]))
    r2 = FakeRunner("model-b", _model_response([("L2", "∀ n, Q n")]))
    result = collect(prob, [r1, r2])
    assert result.consensus is not None
    assert result.consensus.consensus_score == pytest.approx(0.0)


def test_collect_all_fail_consensus_none():
    prob = _problem()
    result = collect(prob, [FailingRunner()])
    assert len(result.entries) == 0
    assert result.consensus is None
    assert len(result.errors) == 1


def test_collect_partial_failure_still_yields_consensus():
    prob = _problem()
    good = FakeRunner("good", _model_response([("L1", "P 0 → Q 0")]))
    result = collect(prob, [good, FailingRunner()])
    assert len(result.entries) == 1
    assert result.consensus is not None
    assert len(result.errors) == 1


def test_collect_empty_runners():
    prob = _problem()
    result = collect(prob, [])
    assert result.entries == ()
    assert result.consensus is None
    assert result.errors == ()


def test_collect_entry_names_match_runners():
    prob = _problem()
    r1 = FakeRunner("alpha", _model_response([("L1", "P 0")]))
    r2 = FakeRunner("beta", _model_response([("L2", "Q 0")]))
    result = collect(prob, [r1, r2])
    names = [name for name, _ in result.entries]
    assert names == ["alpha", "beta"]


def test_collect_via_openai_runner():
    """End-to-end with a mock HTTP transport — exercises the real OpenAICompatibleRunner."""
    prob = _problem()

    def handler(request: httpx.Request) -> httpx.Response:
        content = _model_response([("L1", "P 0 → Q 0"), ("L2", "∀ n, P n")])
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "choices": [{"message": {"role": "assistant", "content": content}}],
            },
        )

    runner = OpenAICompatibleRunner("test-model", transport=httpx.MockTransport(handler))
    result = collect(prob, [runner])
    assert len(result.entries) == 1
    assert result.consensus is not None
