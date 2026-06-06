"""Verify generated artifacts against live Lean and score them. Runs on the Lean host (ren4).

    PG_LEAN_PROJECT=/models/proving-ground-lean \
      python scripts/score_artifacts.py problems/first-run.json artifacts.json runs.json

Then build the leaderboard with: proving-ground leaderboard runs.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from proving_ground.checker import LeanInteractChecker, artifact_from_dict
from proving_ground.corpus import load_corpus
from proving_ground.models import Score, ScoreKind
from proving_ground.results import dump_results
from proving_ground.runner import to_run_result
from proving_ground.scoring import score_decomposition


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("problems", help="Problem set JSON (corpus format).")
    ap.add_argument("artifacts", help="artifacts.json from generate_artifacts.py.")
    ap.add_argument("out", help="Where to write the RunResults JSON.")
    ap.add_argument("--timestamp", required=True, help="ISO-8601 stamp for this run.")
    args = ap.parse_args(argv)

    problems = {p.id: p for p in load_corpus(args.problems)}
    with open(args.artifacts, encoding="utf-8") as f:
        bundle = json.load(f)
    model = bundle["model"]

    checker = LeanInteractChecker(project_dir=os.environ.get("PG_LEAN_PROJECT"))

    results = []
    for rec in bundle["records"]:
        pid = rec["problem_id"]
        problem = problems[pid]
        if not rec.get("ok"):
            score = Score(0.0, ScoreKind.NONE, 0.0, 0.0, (), f"generation failed: {rec.get('error')}")
        else:
            artifact = artifact_from_dict(rec["artifact"])
            decomp = checker.check(artifact)
            score = score_decomposition(decomp)
        print(f"  {pid} [{problem.tier.value}]: {score.value:.3f} ({score.kind.value})", file=sys.stderr)
        results.append(to_run_result(problem, model=model, score=score, timestamp=args.timestamp))

    dump_results(results, args.out)
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
