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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
