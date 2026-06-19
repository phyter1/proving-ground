"""Run a multi-model collect against a problem from the corpus.

Usage:
    python scripts/run_collect.py --config fleet-collect-config-ren1.json \
        --problem-id twin-primes --corpus problems/benchmark-v1.json \
        --out runs/collection-twin-primes-ren1-v4.json

    # Run k=5 independent collections, auto-naming v1..v5:
    python scripts/run_collect.py --config fleet-collect-config-ren1-local.json \
        --problem-id legendre --corpus problems/benchmark-v1.json \
        --out runs/collection-legendre-ren1-local --k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proving_ground.collector import collect
from proving_ground.hardness import is_confusion_non_degenerate, is_degenerate
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
                required_predicates=tuple(item.get("required_predicates", [])),
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


def _next_version(out_prefix: str) -> str:
    """Return next vN path that doesn't exist, starting from v1."""
    n = 1
    while True:
        path = Path(f"{out_prefix}-v{n}.json")
        if not path.exists():
            return str(path)
        n += 1


def _run_once(problem: Problem, runners: list[OpenAICompatibleRunner], out_path: Path) -> None:
    print(f"Collecting {problem.id!r} → {out_path.name} with {len(runners)} models...")
    for r in runners:
        print(f"  - {r.name} ({r.model} @ {r.base_url})")

    result = collect(problem, runners)

    _raw_map = dict(result.raw_responses)
    _RAW_TRUNCATE = 3000

    output = {
        "problem_id": result.problem_id,
        "target_statement": problem.statement,
        "n_models": len(runners),
        "n_degenerate": sum(1 for _, d in result.entries if is_degenerate(d)),
        "n_errors": len(result.errors),
        "consensus": {
            "consensus_score": result.consensus.consensus_score if result.consensus else None,
            "hardness_score": result.consensus.hardness_score if result.consensus else None,
            "n_invalid": result.consensus.n_invalid if result.consensus else None,
            "n_distinct_models": result.consensus.n_distinct_models if result.consensus else None,
            "novel_statements": list(result.consensus.novel_statements) if result.consensus else [],
            "canonical_conjuncts": (
                sorted(result.consensus.canonical_conjuncts)
                if result.consensus and result.consensus.canonical_conjuncts is not None
                else None
            ),
            "n_canonical_match": result.consensus.n_canonical_match if result.consensus else None,
            "n_key_term_absent": result.consensus.n_key_term_absent if result.consensus else None,
        } if result.consensus else None,
        "entries": [
            {
                "model": name,
                "n_subgoals": len(d.subgoals),
                "subgoals": [sg.statement for sg in d.subgoals],
                "is_degenerate": is_degenerate(d),
                "is_confusion": is_confusion_non_degenerate(d),
            }
            for name, d in result.entries
        ],
        "errors": [{"model": m, "error": e} for m, e in result.errors],
        "raw_responses": [
            {
                "model": name,
                "truncated": len(text) > _RAW_TRUNCATE,
                "text": text[:_RAW_TRUNCATE],
            }
            for name, text in result.raw_responses
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Saved to {out_path}")
    print(f"  Consensus: {output['consensus']}")
    if result.errors:
        print(f"  Errors: {result.errors}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", required=True,
                        help="Output path. With --k, treated as prefix and versioned automatically.")
    parser.add_argument("--k", type=int, default=1,
                        help="Number of independent collection runs (default 1). "
                             "With k>1, --out is treated as a path prefix and each run "
                             "is saved as <prefix>-v1.json, <prefix>-v2.json, ... "
                             "skipping versions that already exist.")
    args = parser.parse_args()

    problem = load_problem(args.corpus, args.problem_id)
    runners = runners_from_config(args.config)

    if args.k == 1:
        _run_once(problem, runners, Path(args.out))
    else:
        for i in range(args.k):
            out_path = Path(_next_version(args.out))
            print(f"\n[{i+1}/{args.k}] ", end="")
            _run_once(problem, runners, out_path)
        print(f"\nCompleted {args.k} runs.")


if __name__ == "__main__":
    main()
