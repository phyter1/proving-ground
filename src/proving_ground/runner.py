"""The model runner: prompt a model, get raw text, hand off to extraction.

A :class:`ModelRunner` is a thin, provider-agnostic completion interface. The concrete
:class:`OpenAICompatibleRunner` speaks the OpenAI ``/v1/chat/completions`` shape, which the
fleet router at ``http://ren3.local:3000/v1`` and the cloud APIs all expose. Crucially the
runner takes an injectable httpx transport/client so the whole path is testable with no
network (see ``tests/test_runner.py`` and :class:`httpx.MockTransport`).

This module produces a :class:`~proving_ground.checker.ProofArtifact`; it does NOT score.
Scoring is the checker + scorer's job. :func:`to_run_result` is the seam that lets the
orchestrator assemble a :class:`~proving_ground.models.RunResult` once it has a score and a
caller-supplied timestamp (the harness owns clocks — this module never calls ``now()``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from proving_ground.checker import ProofArtifact
from proving_ground.extract import build_prompt, extract_artifact
from proving_ground.models import Problem, RunResult, Score

DEFAULT_BASE_URL = "http://ren3.local:3000/v1"
DEFAULT_TIMEOUT = 600.0  # frontier proofs are slow; generous default, overridable.


class RunnerError(RuntimeError):
    """Raised when the model endpoint fails or returns an unusable response."""


class ModelRunner(ABC):
    """A provider-agnostic chat completion interface.

    The only operation a runner must support is turning a list of chat messages into a
    single response string. Everything provider-specific (auth, endpoint shape, retries)
    lives in the concrete implementation.
    """

    #: Identifier of the underlying model, for the leaderboard (e.g. "fleet:ren4/qwen3.5:9b").
    name: str

    @abstractmethod
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the model's response text for the given chat messages."""
        raise NotImplementedError


class OpenAICompatibleRunner(ModelRunner):
    """Calls any OpenAI-compatible ``/v1/chat/completions`` endpoint via httpx.

    Defaults to the fleet router for $0 local inference. A ``transport`` or a fully-built
    ``client`` can be injected so tests run without network (use :class:`httpx.MockTransport`).

    Args:
        model: The model id to request (becomes ``RunnerError`` if the endpoint rejects it).
        base_url: OpenAI-compatible base, e.g. ``http://ren3.local:3000/v1``.
        api_key: Optional bearer token (cloud providers); omit for the local router.
        transport: Optional httpx transport (e.g. ``httpx.MockTransport``) for testing.
        client: Optional pre-built ``httpx.Client``; takes precedence over ``transport``.
        timeout: Request timeout in seconds.
        temperature: Sampling temperature passed through to the endpoint.
        extra_body: Extra JSON fields merged into the request payload.
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.0,
        extra_body: dict[str, object] | None = None,
    ) -> None:
        self.model = model
        self.name = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.extra_body = dict(extra_body) if extra_body else {}

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(transport=transport, timeout=timeout)
            self._owns_client = True

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            **self.extra_body,
        }
        try:
            resp = self._client.post(self.endpoint, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise RunnerError(f"Request to {self.endpoint} failed: {exc}") from exc

        if resp.status_code != httpx.codes.OK:
            raise RunnerError(
                f"Endpoint {self.endpoint} returned HTTP {resp.status_code}: "
                f"{resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise RunnerError(
                f"Endpoint {self.endpoint} returned non-JSON body: {resp.text[:500]}"
            ) from exc

        return _content_from_chat_response(data, self.endpoint)

    def close(self) -> None:
        """Close the underlying client if this runner created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAICompatibleRunner:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _content_from_chat_response(data: object, endpoint: str) -> str:
    """Pull the assistant message text out of an OpenAI-style chat completion body."""
    if not isinstance(data, dict):
        raise RunnerError(f"Endpoint {endpoint} returned a non-object JSON response.")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RunnerError(f"Endpoint {endpoint} response had no choices: {data}")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RunnerError(f"Endpoint {endpoint} response had empty message content.")
    return content


def attempt(problem: Problem, runner: ModelRunner) -> ProofArtifact:
    """Run one full attempt: build the prompt, complete it, extract the artifact.

    Raises:
        RunnerError: if the model call fails.
        ExtractionError: if the response cannot be parsed into a ProofArtifact.
    """
    messages = build_prompt(problem)
    response_text = runner.complete(messages)
    return extract_artifact(problem, response_text)


def to_run_result(
    problem: Problem,
    model: str,
    score: Score,
    timestamp: str,
    artifact_ref: str | None = None,
) -> RunResult:
    """Assemble a :class:`RunResult` from an already-computed score.

    The score comes from the checker + scorer (not this module). The timestamp is supplied
    by the caller — the harness owns clocks; this never calls ``datetime.now()``.
    """
    return RunResult(
        model=model,
        problem_id=problem.id,
        tier=problem.tier,
        score=score,
        timestamp=timestamp,
        artifact_ref=artifact_ref,
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "ModelRunner",
    "OpenAICompatibleRunner",
    "RunnerError",
    "attempt",
    "to_run_result",
]
