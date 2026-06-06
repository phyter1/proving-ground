"""Tests for the model runner — all network-free via httpx.MockTransport / fakes."""

from __future__ import annotations

import json

import httpx
import pytest

from proving_ground.checker import ProofArtifact
from proving_ground.models import Problem, Score, ScoreKind, Tier
from proving_ground.runner import (
    DEFAULT_BASE_URL,
    ClaudeCodeRunner,
    ModelRunner,
    OpenAICompatibleRunner,
    RunnerError,
    attempt,
    to_run_result,
)


def _problem(**kw) -> Problem:
    defaults = dict(
        id="conj-7",
        statement="theorem target (n : ℕ) : P n := by sorry",
        tier=Tier.WEAKLY_OPEN,
        source="sorrydb",
        preamble="import Mathlib",
    )
    defaults.update(kw)
    return Problem(**defaults)


def _chat_body(content: str) -> dict:
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


# --- OpenAICompatibleRunner.complete: canned response, no network ---------

def test_complete_parses_openai_style_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_chat_body("hello from the model"))

    runner = OpenAICompatibleRunner(
        "fleet:ren4/qwen3.5:9b",
        transport=httpx.MockTransport(handler),
    )
    out = runner.complete([{"role": "user", "content": "hi"}])

    assert out == "hello from the model"
    assert captured["url"] == f"{DEFAULT_BASE_URL}/chat/completions"
    assert captured["payload"]["model"] == "fleet:ren4/qwen3.5:9b"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]
    # No api_key => no Authorization header (local router).
    assert captured["auth"] is None


def test_complete_sends_bearer_when_api_key_set():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_chat_body("ok"))

    runner = OpenAICompatibleRunner(
        "claude-opus",
        base_url="https://api.example.com/v1",
        api_key="secret-token",
        transport=httpx.MockTransport(handler),
    )
    runner.complete([{"role": "user", "content": "hi"}])
    assert captured["auth"] == "Bearer secret-token"


def test_complete_raises_on_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    runner = OpenAICompatibleRunner("m", transport=httpx.MockTransport(handler))
    with pytest.raises(RunnerError):
        runner.complete([{"role": "user", "content": "hi"}])


def test_complete_raises_on_empty_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_body("   "))

    runner = OpenAICompatibleRunner("m", transport=httpx.MockTransport(handler))
    with pytest.raises(RunnerError):
        runner.complete([{"role": "user", "content": "hi"}])


def test_complete_raises_on_missing_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    runner = OpenAICompatibleRunner("m", transport=httpx.MockTransport(handler))
    with pytest.raises(RunnerError):
        runner.complete([{"role": "user", "content": "hi"}])


def test_runner_accepts_injected_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_body("via injected client"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    runner = OpenAICompatibleRunner("m", client=client)
    assert runner.complete([{"role": "user", "content": "hi"}]) == "via injected client"


# --- attempt: end to end with a fake runner -------------------------------

class _FakeRunner(ModelRunner):
    def __init__(self, response: str, name: str = "fake-model") -> None:
        self.response = response
        self.name = name
        self.last_messages: list[dict[str, str]] | None = None

    def complete(self, messages):
        self.last_messages = messages
        return self.response


_DECOMP_RESPONSE = """\
```lean
import Mathlib

lemma step_a (n : ℕ) : A n := by sorry
lemma step_b (n : ℕ) : B n := by decide

theorem target (n : ℕ) : P n := by
  exact absurd (step_a n) (step_b n)
```
```json
{"subgoal_ids": ["step_a", "step_b"]}
```
"""


def test_attempt_produces_artifact_end_to_end():
    p = _problem()
    runner = _FakeRunner(_DECOMP_RESPONSE)
    art = attempt(p, runner)

    assert isinstance(art, ProofArtifact)
    assert art.target_id == p.id
    assert art.target_statement == p.statement
    assert art.subgoal_ids == ("step_a", "step_b")
    assert "step_a" in art.lean_source
    # attempt built a real prompt and fed it to the runner.
    assert runner.last_messages is not None
    assert runner.last_messages[0]["role"] == "system"
    assert p.statement in runner.last_messages[1]["content"]


# --- to_run_result ---------------------------------------------------------

def test_to_run_result_builds_correct_row():
    p = _problem()
    score = Score(
        value=0.5,
        kind=ScoreKind.REDUCTION,
        discharged_weight=1.0,
        total_weight=2.0,
        remaining_open_ids=("step_a",),
        rationale="1 of 2 subgoals discharged",
    )
    rr = to_run_result(
        p,
        model="fleet:ren4/qwen3.5:9b",
        score=score,
        timestamp="2026-06-06T12:00:00Z",
        artifact_ref="artifacts/conj-7.json",
    )

    assert rr.model == "fleet:ren4/qwen3.5:9b"
    assert rr.problem_id == p.id
    assert rr.tier == p.tier
    assert rr.score is score
    assert rr.timestamp == "2026-06-06T12:00:00Z"
    assert rr.artifact_ref == "artifacts/conj-7.json"


def test_to_run_result_artifact_ref_optional():
    p = _problem()
    score = Score(0.0, ScoreKind.NONE, 0.0, 0.0, (), "no progress")
    rr = to_run_result(p, model="m", score=score, timestamp="2026-06-06T00:00:00Z")
    assert rr.artifact_ref is None


def test_claude_code_runner_invokes_cli_and_returns_output():
    captured = {}

    def fake_invoke(user, system):
        captured["user"] = user
        captured["system"] = system
        return "```lean\ntheorem reduction : True := trivial\n```"

    runner = ClaudeCodeRunner(model="opus", invoke=fake_invoke)
    assert runner.name == "claude-code/opus"

    out = runner.complete(
        [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USR"}]
    )
    assert "reduction" in out
    assert captured["system"] == "SYS"
    assert captured["user"] == "USR"


def test_claude_code_runner_end_to_end_with_extract():
    response = (
        "Here is my reduction.\n\n"
        "```lean\ntheorem sg_a : True := trivial\n"
        "theorem reduction : True → True := id\n```\n\n"
        '```json\n{"subgoal_ids": ["sg_a"], "root_name": "reduction"}\n```\n'
    )
    runner = ClaudeCodeRunner(invoke=lambda user, system: response)
    p = _problem(statement="True")
    artifact = attempt(p, runner)
    assert artifact.target_statement == "True"
    assert artifact.subgoal_ids == ("sg_a",)
    assert artifact.root_name == "reduction"
