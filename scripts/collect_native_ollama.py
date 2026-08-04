"""Collect a single problem response via native Ollama API (supports think:false).

Use when the OAI-compat endpoint doesn't suppress thinking mode.

Usage:
    python scripts/collect_native_ollama.py \
        --problem-id twin-primes \
        --corpus problems/benchmark-v1.json \
        --host http://primus.local:11434 \
        --model qwen3.6:35b-a3b \
        --runner-name primus/qwen3.6-35b \
        --out runs/collection-twin-primes-primus-v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proving_ground.collector import artifact_to_unverified_decomposition
from proving_ground.extract import ExtractionError, build_prompt, extract_artifact
from proving_ground.hardness import compute_consensus, is_degenerate, is_confusion_non_degenerate
from proving_ground.models import Problem, Tier


def load_problem(corpus_path: str, problem_id: str) -> Problem:
    with open(corpus_path) as f:
        items = json.load(f)
    for item in items:
        if item["id"] == problem_id:
            return Problem(
                id=item["id"],
                title=item.get("title", item["id"]),
                statement=item["statement"],
                tier=Tier(item.get("tier", "open")),
                preamble=item.get("preamble", "import Mathlib"),
                source=item.get("source", ""),
                references=tuple(item.get("references", [])),
                proved_after=item.get("proved_after"),
                metadata=item.get("metadata", {}),
                required_predicates=tuple(item.get("required_predicates", [])),
            )
    raise KeyError(f"Problem {problem_id!r} not found in {corpus_path}")


def call_native_ollama(host: str, model: str, messages: list[dict], timeout: float = 300) -> str:
    """Call Ollama /api/chat with think:false and return the assistant content."""
    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "think": False,
        "stream": False,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--corpus", default="problems/benchmark-v1.json")
    parser.add_argument("--host", default="http://primus.local:11434")
    parser.add_argument("--model", default="qwen3.6:35b-a3b")
    parser.add_argument("--runner-name", default="primus/qwen3.6-35b")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    problem = load_problem(args.corpus, args.problem_id)
    messages = build_prompt(problem)

    print(f"Querying {args.runner_name} for {problem.id!r}...", flush=True)
    t0 = time.time()
    try:
        response = call_native_ollama(args.host, args.model, messages, timeout=args.timeout)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    elapsed = time.time() - t0
    print(f"  Got response in {elapsed:.1f}s ({len(response)} chars)", flush=True)

    entries = []
    errors = []
    decompositions = []

    try:
        artifact = extract_artifact(problem, response)
        decomp = artifact_to_unverified_decomposition(artifact)
        sg_statements = [sg.statement for sg in decomp.subgoals]
        deg = is_degenerate(decomp)
        conf = is_confusion_non_degenerate(decomp)
        entry = {
            "model": args.runner_name,
            "n_subgoals": len(sg_statements),
            "subgoals": sg_statements,
            "is_degenerate": deg,
            "is_confusion": conf,
        }
        print(f"  Extracted: {len(sg_statements)} subgoals, degenerate={deg}")
        for sg in sg_statements:
            print(f"    {sg}")
        entries.append(entry)
        decompositions.append(decomp)
    except ExtractionError as e:
        print(f"  ExtractionError: {e}")
        errors.append({"model": args.runner_name, "error": str(e)})

    consensus = (
        compute_consensus(
            problem.id,
            decompositions,
            model_ids=[args.runner_name] * len(decompositions),
            required_predicates=tuple(problem.required_predicates),
        )
        if decompositions
        else None
    )

    result = {
        "problem_id": problem.id,
        "target_statement": problem.statement,
        "n_models": 1,
        "n_degenerate": sum(1 for e in entries if e["is_degenerate"]),
        "n_errors": len(errors),
        "consensus": (
            {
                "consensus_score": consensus.consensus_score,
                "hardness_score": consensus.hardness_score,
                "novel_statements": list(consensus.novel_statements),
                "n_distinct_models": consensus.n_distinct_models,
                "n_invalid": consensus.n_invalid,
            }
            if consensus
            else None
        ),
        "entries": entries,
        "errors": errors,
    }

    out_path = Path(args.out)
    if not out_path.suffix:
        out_path = out_path.with_suffix(".json")
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
