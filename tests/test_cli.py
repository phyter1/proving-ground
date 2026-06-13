"""CLI smoke tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from proving_ground.cli import main


def test_score_example_problem(capsys):
    example = Path(__file__).parent.parent / "problems" / "example-reduction.json"
    rc = main(["score", str(example)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # base-case (w=1) discharged, inductive-step (w=3) open => 1/4.
    assert out["value"] == 0.25
    assert out["kind"] == "reduction"
    assert out["remaining_open_ids"] == ["inductive-step"]


def _model_response_for_cli(lemmas: list[tuple[str, str]], target: str) -> str:
    """Build a well-formed model response for CLI collect tests."""
    lines = ["import Mathlib", ""]
    for name, ty in lemmas:
        lines.append(f"theorem {name} : {ty} := by sorry")
    lines += [
        "",
        f"theorem reduction (h : {lemmas[0][0]}_type) : {target} := by exact h",
        "",
    ]
    lean = "\n".join(lines)
    ids = json.dumps({"subgoal_ids": [n for n, _ in lemmas], "root_name": "reduction"})
    return f"```lean\n{lean}\n```\n\n```json\n{ids}\n```"


def test_collect_output_includes_n_degenerate(tmp_path):
    """collect subcommand output must include n_degenerate and is_degenerate per entry."""
    corpus_path = Path(__file__).parent.parent / "problems" / "benchmark-v1.json"

    # Two mock runners: one degenerate (sole subgoal == target), one real.
    target = "∀ n : ℕ, Even n ∨ Odd n"
    degenerate_resp = _model_response_for_cli([("degen", target)], target)
    real_resp = _model_response_for_cli(
        [("base", "Even 0 ∨ Odd 0"), ("step", "Even (S k) ∨ Odd (S k)")], target
    )

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        content = degenerate_resp if call_count == 0 else real_resp
        call_count += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": content}}],
            },
        )

    config = {
        "models": [
            {"name": "model-a", "model": "test-a", "base_url": "http://localhost:9999/v1"},
            {"name": "model-b", "model": "test-b", "base_url": "http://localhost:9999/v1"},
        ]
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    out_path = tmp_path / "result.json"

    with patch("proving_ground.runner.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client_cls.return_value._owns_client = True
        # Make the post method use our handler
        mock_client_cls.return_value.post.side_effect = lambda url, **kw: handler(
            httpx.Request("POST", url)
        )

        rc = main(
            [
                "collect",
                "--corpus", str(corpus_path),
                "--problem-id", "tractable-even-or-odd",
                "--config", str(config_path),
                "--out", str(out_path),
            ]
        )

    assert rc == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text())

    assert "n_degenerate" in data
    assert "entries" in data
    for entry in data["entries"]:
        assert "is_degenerate" in entry


def test_collect_temperature_forwarded(tmp_path):
    """temperature in model config must be passed through to the runner."""
    corpus_path = Path(__file__).parent.parent / "problems" / "benchmark-v1.json"
    target = "∀ n : ℕ, Even n ∨ Odd n"
    resp = _model_response_for_cli(
        [("base", "Even 0 ∨ Odd 0"), ("step", "Even (S k) ∨ Odd (S k)")], target
    )

    seen_temps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen_temps.append(payload.get("temperature"))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": resp}}],
            },
        )

    config = {
        "models": [
            {
                "name": "hot-model",
                "model": "test-hot",
                "base_url": "http://localhost:9999/v1",
                "temperature": 0.7,
            }
        ]
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    with patch("proving_ground.runner.httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.post.side_effect = lambda url, **kw: handler(
            httpx.Request("POST", url, content=json.dumps(kw.get("json", {})).encode())
        )
        rc = main(
            [
                "collect",
                "--corpus", str(corpus_path),
                "--problem-id", "tractable-even-or-odd",
                "--config", str(config_path),
            ]
        )

    assert rc == 0
    assert seen_temps == [0.7]
