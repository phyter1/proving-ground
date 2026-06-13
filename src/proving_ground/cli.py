"""Minimal CLI. Scores a decomposition supplied as JSON.

This is the offline entrypoint: it takes already-verified verdicts (as produced by a
Lean-backed checker, or hand-authored for testing) and applies the metric. The Lean
``check`` subcommand is added in the Lean-integration milestone.

    proving-ground score path/to/decomposition.json
    cat decomposition.json | proving-ground score -

JSON shape::

    {
      "target_id": "erdos-124",
      "target_statement": "<lean type>",
      "root_implication_verified": true,
      "statement_matches_target": true,
      "axioms_clean": true,
      "subgoals": [
        {"id": "L1", "statement": "<lean type>", "weight": 1.0, "discharged": true},
        {"id": "L2", "statement": "<lean type>", "weight": 2.0, "discharged": false}
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from proving_ground.models import Decomposition, Subgoal
from proving_ground.scoring import score_decomposition


def _load(path: str) -> dict:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return json.loads(raw)


def _decomposition_from_dict(data: dict) -> Decomposition:
    subgoals = tuple(
        Subgoal(
            id=sg["id"],
            statement=sg["statement"],
            weight=float(sg.get("weight", 1.0)),
            discharged=bool(sg.get("discharged", False)),
        )
        for sg in data.get("subgoals", [])
    )
    return Decomposition(
        target_id=data["target_id"],
        target_statement=data["target_statement"],
        subgoals=subgoals,
        root_implication_verified=bool(data.get("root_implication_verified", False)),
        statement_matches_target=bool(data.get("statement_matches_target", False)),
        axioms_clean=bool(data.get("axioms_clean", False)),
    )


def _cmd_score(args: argparse.Namespace) -> int:
    decomp = _decomposition_from_dict(_load(args.path))
    score = score_decomposition(decomp)
    out = asdict(score)
    out["kind"] = score.kind.value
    print(json.dumps(out, indent=2))
    return 0


def _cmd_leaderboard(args: argparse.Namespace) -> int:
    # Imported lazily so `score` works even if optional pieces change.
    from proving_ground.leaderboard import render_markdown, write_site
    from proving_ground.results import aggregate, load_results

    board = aggregate(load_results(args.results))
    if args.out:
        write_site(board, args.out)
        print(f"Wrote leaderboard site to {args.out}")
    else:
        print(render_markdown(board))
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    """Run multiple models against a problem and print the hardness signal."""
    from dataclasses import asdict

    from proving_ground.collector import collect
    from proving_ground.corpus import load_corpus
    from proving_ground.hardness import is_degenerate
    from proving_ground.runner import OpenAICompatibleRunner

    corpus = load_corpus(args.corpus)
    problem = next((p for p in corpus if p.id == args.problem_id), None)
    if problem is None:
        print(f"error: problem '{args.problem_id}' not found in {args.corpus}", file=sys.stderr)
        return 1

    config = json.loads(open(args.config, encoding="utf-8").read())
    runners = [
        OpenAICompatibleRunner(
            m["model"],
            base_url=m.get("base_url", "http://ren3.local:3000/v1"),
            api_key=m.get("api_key"),
            temperature=float(m.get("temperature", 0.0)),
        )
        for m in config["models"]
    ]
    for r, m in zip(runners, config["models"]):
        r.name = m.get("name", r.name)

    result = collect(problem, runners)

    out: dict = {
        "problem_id": result.problem_id,
        "n_models": len(result.entries),
        "n_degenerate": result.consensus.n_degenerate if result.consensus is not None else 0,
        "n_errors": len(result.errors),
        "consensus": (
            {
                "consensus_score": result.consensus.consensus_score,
                "hardness_score": result.consensus.hardness_score,
                "novel_statements": sorted(result.consensus.novel_statements),
            }
            if result.consensus is not None
            else None
        ),
        "entries": [
            {
                "model": name,
                "subgoal_statements": [sg.statement for sg in decomp.subgoals],
                "is_degenerate": is_degenerate(decomp),
            }
            for name, decomp in result.entries
        ],
        "errors": [{"model": m, "error": e} for m, e in result.errors],
    }

    dest = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    print(json.dumps(out, indent=2), file=dest)
    if args.out:
        dest.close()
        print(f"Wrote collection result to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proving-ground")
    sub = parser.add_subparsers(dest="command", required=True)

    p_score = sub.add_parser("score", help="Score a decomposition from JSON.")
    p_score.add_argument("path", help="Path to JSON file, or '-' for stdin.")
    p_score.set_defaults(func=_cmd_score)

    p_lb = sub.add_parser("leaderboard", help="Aggregate RunResults into a leaderboard.")
    p_lb.add_argument("results", help="Path to a JSON array of RunResults.")
    p_lb.add_argument(
        "--out", help="Output dir for a static HTML site. If omitted, prints markdown."
    )
    p_lb.set_defaults(func=_cmd_leaderboard)

    p_collect = sub.add_parser(
        "collect",
        help="Run multiple models against a problem; print the hardness signal.",
    )
    p_collect.add_argument("--corpus", required=True, help="Path to corpus JSON.")
    p_collect.add_argument("--problem-id", required=True, dest="problem_id",
                           help="Problem id to attempt.")
    p_collect.add_argument("--config", required=True,
                           help='JSON file: {"models": [{"name":..., "base_url":..., '
                                '"model":...}, ...]}')
    p_collect.add_argument("--out", help="Write JSON output to file (default: stdout).")
    p_collect.set_defaults(func=_cmd_collect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
