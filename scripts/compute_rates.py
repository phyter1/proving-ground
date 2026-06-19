"""Compute per-model degeneracy rates across multiple runs for a problem.

Usage:
    python scripts/compute_rates.py --problem-id legendre --runs-dir runs/
    python scripts/compute_rates.py --problem-id collatz --runs-dir runs/
    python scripts/compute_rates.py --problem-id legendre --compare collatz --runs-dir runs/
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a Bernoulli rate."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    center = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / (1 + z**2 / n)
    return (max(0.0, center - margin), min(1.0, center + margin))


def load_runs(problem_id: str, runs_dir: Path) -> list[dict]:
    pattern = f"collection-{problem_id}-*.json"
    files = sorted(runs_dir.glob(pattern))
    if not files:
        print(f"No run files found matching {runs_dir}/{pattern}", file=sys.stderr)
        sys.exit(1)
    runs = []
    for f in files:
        with open(f) as fp:
            data = json.load(fp)
            data["_file"] = f.name
            runs.append(data)
    return runs


def compute_model_rates(runs: list[dict]) -> dict[str, dict]:
    """Return per-model stats: attempts, degenerate, errors, degeneracy_rate."""
    stats: dict[str, dict] = {}
    for run in runs:
        for entry in run.get("entries", []):
            model = entry["model"]
            if model not in stats:
                stats[model] = {"attempts": 0, "degenerate": 0, "non_degenerate": 0}
            stats[model]["attempts"] += 1
            if entry["is_degenerate"]:
                stats[model]["degenerate"] += 1
            else:
                stats[model]["non_degenerate"] += 1
        for err in run.get("errors", []):
            model = err["model"]
            if model not in stats:
                stats[model] = {"attempts": 0, "degenerate": 0, "non_degenerate": 0}
    for model, s in stats.items():
        n = s["attempts"]
        s["degeneracy_rate"] = s["degenerate"] / n if n > 0 else None
        s["non_degenerate_rate"] = s["non_degenerate"] / n if n > 0 else None
    return stats


def print_rates(problem_id: str, runs: list[dict], stats: dict[str, dict]) -> None:
    n_runs = len(runs)
    files = [r["_file"] for r in runs]
    print(f"\n{'='*60}")
    print(f"Problem: {problem_id}  ({n_runs} run{'s' if n_runs != 1 else ''})")
    print(f"Files: {', '.join(files)}")
    print(f"{'='*60}")
    print(f"{'Model':<30} {'N':>4} {'Degen':>6} {'Rate':>6} {'95% CI':>15} {'Non-deg':>8} {'NDRate':>7}")
    print(f"{'-'*30} {'-'*4} {'-'*6} {'-'*6} {'-'*15} {'-'*8} {'-'*7}")
    for model, s in sorted(stats.items()):
        n = s["attempts"]
        rate = f"{s['degeneracy_rate']:.0%}" if s['degeneracy_rate'] is not None else "N/A"
        nd_rate = f"{s['non_degenerate_rate']:.0%}" if s['non_degenerate_rate'] is not None else "N/A"
        if n > 0:
            lo, hi = wilson_ci(s["degenerate"], n)
            ci = f"[{lo:.0%}, {hi:.0%}]"
        else:
            ci = "N/A"
        print(f"{model:<30} {n:>4} {s['degenerate']:>6} {rate:>6} {ci:>15} {s['non_degenerate']:>8} {nd_rate:>7}")
    print()


def print_non_degenerate_content(problem_id: str, runs: list[dict]) -> None:
    """Print content of non-degenerate runs for manual structured/confusion classification."""
    non_degen = []
    for run in runs:
        for entry in run.get("entries", []):
            if not entry["is_degenerate"]:
                non_degen.append((run["_file"], entry["model"], entry["subgoals"]))
    if not non_degen:
        return
    print(f"\n--- Non-degenerate outputs for {problem_id} (manual classify: structured/confusion) ---")
    for fname, model, subgoals in non_degen:
        print(f"  [{fname}] {model}:")
        for sg in subgoals:
            print(f"    {sg}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--compare", help="Optional second problem to compare against")
    parser.add_argument("--runs-dir", default="runs/")
    parser.add_argument("--content", action="store_true", help="Show non-degenerate content for classification")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    runs = load_runs(args.problem_id, runs_dir)
    stats = compute_model_rates(runs)
    print_rates(args.problem_id, runs, stats)

    if args.content:
        print_non_degenerate_content(args.problem_id, runs)

    if args.compare:
        cmp_runs = load_runs(args.compare, runs_dir)
        cmp_stats = compute_model_rates(cmp_runs)
        print_rates(args.compare, cmp_runs, cmp_stats)

        if args.content:
            print_non_degenerate_content(args.compare, cmp_runs)

        print(f"\n{'='*60}")
        print(f"Comparison: {args.problem_id} vs {args.compare}")
        print(f"Hypothesis: {args.problem_id} should have LOWER degeneracy rate")
        print(f"(literature anchors → structured non-degeneracy)")
        print(f"{'='*60}")
        all_models = sorted(set(stats) | set(cmp_stats))
        for model in all_models:
            a = stats.get(model, {})
            b = cmp_stats.get(model, {})
            a_rate = a.get("degeneracy_rate")
            b_rate = b.get("degeneracy_rate")
            if a_rate is not None and b_rate is not None:
                direction = "✓" if a_rate <= b_rate else "✗"
                print(f"  {model}: {args.problem_id}={a_rate:.0%} vs {args.compare}={b_rate:.0%} {direction}")
            else:
                print(f"  {model}: insufficient data")


if __name__ == "__main__":
    main()
