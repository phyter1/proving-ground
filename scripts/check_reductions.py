"""Lean reduction auto-verifiability check.

For each model in a collection run, tests whether the model's proposed subgoal types
admit a short verified proof of the reduction: (h1 : T1) → ... → (hk : Tk) → target.

This is the discrimination instrument for the persistent hardness gap:
- tractable problems: at least one model's decomposition should be auto-closable
- genuinely hard / confused decompositions: no model's reduction should close

Run on ren4 (ELAN_HOME=/models/.elan, lean-interact installed):
    ELAN_HOME=/models/.elan PATH=/models/.elan/bin:$PATH \\
        uv run python scripts/check_reductions.py runs/collection-calib-tractable-even-or-odd-v1.json
    ELAN_HOME=/models/.elan PATH=/models/.elan/bin:$PATH \\
        uv run python scripts/check_reductions.py runs/collection-goldbach-3model-v1.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


# Tactics to try, in order. If any closes the goal, the reduction is auto-verifiable.
# Conservative set — strong tactics (simp, norm_num) are excluded to avoid marking
# trivially-decidable goals as "hard decompositions that reduce nicely".
TACTICS = [
    "aesop",
    "tauto",
    "simp_all",
    "intro n; induction n with | zero => aesop | succ k ih => aesop",
    "intro n; induction n with | zero => simp_all | succ k ih => simp_all",
    "intro n; exact Nat.rec ‹_› (fun k ih => ‹_› k ih) n",
]

# Per-tactic timeout in seconds. Lean REPL elaboration can be slow with Mathlib loaded.
TACTIC_TIMEOUT = 30


def build_example(subgoal_types: list[str], target: str) -> str:
    """Build a Lean 4 `example` that checks if the reduction closes automatically.

    The example takes each subgoal type as a hypothesis and tries to conclude the target.
    The actual proof attempt uses the tactics in TACTICS — checked by the Lean kernel.
    """
    hyps = " ".join(f"(h{i} : {t})" for i, t in enumerate(subgoal_types))
    return f"example {hyps} : {target} := by\n  first"


def _has_sorry(resp) -> bool:
    """True if the REPL response contains a sorry (warning or remaining goal)."""
    messages = getattr(resp, "messages", []) or []
    for m in messages:
        data = getattr(m, "data", "") or ""
        if "sorry" in data.lower():
            return True
    # lean-interact may expose remaining sorry goals directly.
    sorries = getattr(resp, "sorries", None)
    return bool(sorries)


def check_reduction(
    server,
    mathlib_env: int,
    subgoal_types: list[str],
    target: str,
    *,
    model_label: str = "",
) -> dict:
    """Try to auto-close the reduction and return a result dict."""
    from lean_interact import Command

    result = {
        "model": model_label,
        "n_subgoals": len(subgoal_types),
        "auto_verifiable": False,
        "closing_tactic": None,
        "errors": [],
    }

    if not subgoal_types:
        result["errors"].append("no subgoals")
        return result

    hyps = " ".join(f"(h{i} : {t})" for i, t in enumerate(subgoal_types))

    for tactic in TACTICS:
        # Try one tactic at a time — no sorry sentinel needed.
        cmd = f"example {hyps} : {target} := by\n  {tactic}"

        try:
            resp = server.run(Command(cmd=cmd, env=mathlib_env))
            messages = getattr(resp, "messages", []) or []
            errors = [m for m in messages if getattr(m, "severity", "") == "error"]

            if errors:
                continue  # tactic failed

            if _has_sorry(resp):
                continue  # tactic introduced sorry (shouldn't happen without sorry tactic)

            # No errors, no sorry → genuinely closed.
            result["auto_verifiable"] = True
            result["closing_tactic"] = tactic
            return result

        except Exception as e:
            result["errors"].append(f"{tactic}: {str(e)[:100]}")
            continue

    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: check_reductions.py <collection-run.json> [project_dir]", file=sys.stderr)
        sys.exit(1)

    run_path = Path(sys.argv[1])
    project_dir = sys.argv[2] if len(sys.argv) > 2 else "/models/proving-ground-lean"

    if not run_path.exists():
        print(f"File not found: {run_path}", file=sys.stderr)
        sys.exit(1)

    with run_path.open() as f:
        data = json.load(f)

    problem_id = data.get("problem_id", "unknown")
    target = data.get("target_statement", "")
    entries = data.get("entries", [])
    raw_responses = {r["model"]: r for r in data.get("raw_responses", [])}

    print(f"Problem: {problem_id}")
    print(f"Target:  {target}")
    print(f"Models:  {len(entries)}")
    print(f"Project: {project_dir}")
    print()

    # Check that lake is on PATH.
    import shutil
    if shutil.which("lake") is None:
        print("ERROR: `lake` not on PATH. Set ELAN_HOME=/models/.elan and PATH=/models/.elan/bin:$PATH", file=sys.stderr)
        sys.exit(1)

    from lean_interact import AutoLeanServer, Command, LeanREPLConfig, LocalProject

    print("Starting Lean REPL server (this may take 30-60s for Mathlib)...")
    t0 = time.time()
    config = LeanREPLConfig(project=LocalProject(directory=project_dir))
    server = AutoLeanServer(config)

    # Import Mathlib once; reuse this env for all checks.
    base_resp = server.run(Command(cmd="import Mathlib"))
    mathlib_env = base_resp.env
    elapsed = time.time() - t0
    print(f"Mathlib loaded in {elapsed:.1f}s (env={mathlib_env})\n")

    results = []
    n_auto = 0

    for entry in entries:
        model = entry["model"]
        subgoal_types = entry.get("subgoals", [])
        is_degenerate = entry.get("is_degenerate", False)
        is_confusion = entry.get("is_confusion", False)

        print(f"--- {model} ---")
        if is_degenerate:
            print("  SKIPPED (degenerate)")
            results.append({"model": model, "auto_verifiable": False, "skipped": "degenerate"})
            continue

        print(f"  Subgoals ({len(subgoal_types)}):")
        for i, t in enumerate(subgoal_types):
            print(f"    h{i}: {t}")

        res = check_reduction(
            server, mathlib_env, subgoal_types, target, model_label=model
        )
        results.append(res)

        if res["auto_verifiable"]:
            n_auto += 1
            print(f"  ✓ AUTO-VERIFIABLE via: {res['closing_tactic']}")
        else:
            errs = res.get("errors", [])
            print(f"  ✗ not auto-verifiable" + (f" (errors: {errs[:2]})" if errs else ""))
        print()

    print(f"=== Summary: {n_auto}/{len(entries)} models auto-verifiable ===")
    print(f"problem_id: {problem_id}")
    print(f"n_models: {len(entries)}")
    print(f"n_auto_verifiable: {n_auto}")
    print()

    # Output JSON summary.
    summary = {
        "problem_id": problem_id,
        "target_statement": target,
        "n_models": len(entries),
        "n_auto_verifiable": n_auto,
        "results": results,
    }
    out_path = run_path.parent / f"reduction-check-{run_path.stem}.json"
    with out_path.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
