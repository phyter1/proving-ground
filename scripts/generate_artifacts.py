"""Generate ProofArtifacts by running a model against a problem set. Runs on the model host.

For the Claude Code run: this executes on Ryan's Air (where `claude` is authed) and writes
artifacts.json, which is then shipped to a Lean host (ren4) for verification by
score_artifacts.py. Keeps generation and verification on separate machines.

    python scripts/generate_artifacts.py problems/first-run.json artifacts.json [--model opus]
"""

from __future__ import annotations

import argparse
import json
import sys

from proving_ground.checker import artifact_to_dict
from proving_ground.corpus import load_corpus
from proving_ground.extract import ExtractionError
from proving_ground.runner import ClaudeCodeRunner, RunnerError, attempt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("problems", help="Problem set JSON (corpus format).")
    ap.add_argument("out", help="Where to write artifacts JSON.")
    ap.add_argument("--model", default=None, help="claude --model (e.g. opus, sonnet).")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args(argv)

    problems = load_corpus(args.problems)
    runner = ClaudeCodeRunner(model=args.model, timeout=args.timeout)
    print(f"Model: {runner.name}; {len(problems)} problems", file=sys.stderr)

    records = []
    for p in problems:
        print(f"  attempting {p.id} ...", file=sys.stderr, flush=True)
        try:
            artifact = attempt(p, runner)
            records.append({"problem_id": p.id, "ok": True, "artifact": artifact_to_dict(artifact)})
            print(f"    -> {len(artifact.subgoal_ids)} subgoals", file=sys.stderr)
        except (RunnerError, ExtractionError) as exc:
            records.append({"problem_id": p.id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            print(f"    -> FAILED: {exc}", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"model": runner.name, "records": records}, f, indent=2, ensure_ascii=False)
    print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
