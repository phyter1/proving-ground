"""Run a multi-model collect against a problem from the corpus.

Usage:
    python scripts/run_collect.py --config fleet-collect-config-ren1.json \
        --problem-id twin-primes --corpus problems/benchmark-v1.json \
        --out runs/collection-twin-primes-ren1-v4.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proving_ground.collector import collect
from proving_ground.hardness import is_degenerate
from proving_ground.models import Problem, Tier
from proving_ground.runner import OpenAICompatibleRunner


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
            )
    raise KeyError(f"Problem {problem_id!r} not found in {corpus_path}")


def runners_from_config(config_path: str) -> list[OpenAICompatibleRunner]:
    with open(config_path) as f:
        config = json.load(f)
    runners = []
    for m in config["models"]:
        runner = OpenAICompatibleRunner(
            model=m["model"],
            base_url=m["base_url"],
            timeout=m.get("timeout", 300.0),
            temperature=0.0,
            extra_body=m.get("extra_body"),
        )
        runner.name = m["name"]
        runners.append(runner)
    return runners


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    problem = load_problem(args.corpus, args.problem_id)
    runners = runners_from_config(args.config)

    print(f"Collecting {problem.id!r} with {len(runners)} models...")
    for r in runners:
        print(f"  - {r.name} ({r.model} @ {r.base_url})")

    result = collect(problem, runners)

    output = {
        "problem_id": result.problem_id,
        "n_models": len(runners),
        "n_degenerate": sum(
            1 for _, d in result.entries
            if len(d.subgoals) == 0 or
               (len(d.subgoals) == 1 and d.subgoals[0].statement == problem.statement)
        ),
        "n_errors": len(result.errors),
        "consensus": {
            "consensus_score": result.consensus.consensus_score if result.consensus else None,
            "hardness_score": result.consensus.hardness_score if result.consensus else None,
            "novel_statements": list(result.consensus.novel_statements) if result.consensus else [],
        } if result.consensus else None,
        "entries": [
            {
                "model": name,
                "n_subgoals": len(d.subgoals),
                "subgoals": [sg.statement for sg in d.subgoals],
                "is_degenerate": is_degenerate(d),
            }
            for name, d in result.entries
        ],
        "errors": [{"model": m, "error": e} for m, e in result.errors],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResult saved to {out_path}")
    print(f"Consensus: {output['consensus']}")
    if result.errors:
        print(f"Errors: {result.errors}")


if __name__ == "__main__":
    main()
