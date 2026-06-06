"""Generate ProofArtifacts by running a model against a problem set. Runs on the model host.

Generation runs where the model is reachable (Claude Code on the Air; fleet models via the
ren3 router); the artifacts JSON is then shipped to a Lean host (ren4) for verification by
score_artifacts.py. Keeps generation and verification on separate machines.

    # Claude Code CLI (headless, free):
    python scripts/generate_artifacts.py problems/benchmark-v1.json art-opus.json \
        --runner claude --model opus
    # A fleet model via the OpenAI-compatible router:
    python scripts/generate_artifacts.py problems/benchmark-v1.json art-qwen.json \
        --runner fleet --model qwen3.5:9b --base-url http://ren3.local:3000/v1
"""

from __future__ import annotations

import argparse
import json
import sys

from proving_ground.checker import artifact_to_dict
from proving_ground.corpus import load_corpus
from proving_ground.extract import ExtractionError
from proving_ground.runner import (
    ClaudeCodeRunner,
    OpenAICompatibleRunner,
    RunnerError,
    attempt,
)


def _build_runner(args) -> object:
    if args.runner == "claude":
        return ClaudeCodeRunner(model=args.model, timeout=args.timeout)
    if args.runner == "fleet":
        kw = {"timeout": args.timeout}
        if args.base_url:
            kw["base_url"] = args.base_url
        return OpenAICompatibleRunner(args.model, **kw)
    raise SystemExit(f"unknown --runner {args.runner!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("problems", help="Problem set JSON (corpus format).")
    ap.add_argument("out", help="Where to write artifacts JSON.")
    ap.add_argument("--runner", default="claude", choices=["claude", "fleet"])
    ap.add_argument("--model", default=None, help="Model id (claude: opus/sonnet/haiku).")
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (fleet).")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args(argv)

    problems = load_corpus(args.problems)
    runner = _build_runner(args)
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
