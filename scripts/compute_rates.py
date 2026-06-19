"""Compute per-model degeneracy rates across multiple runs for a problem.

Usage:
    python scripts/compute_rates.py --problem-id legendre --runs-dir runs/
    python scripts/compute_rates.py --problem-id collatz --runs-dir runs/
    python scripts/compute_rates.py --problem-id legendre --compare collatz --runs-dir runs/
    python scripts/compute_rates.py --problem-id legendre --three-way --runs-dir runs/

Three-way classification:
    degenerate  — model restated the target or near-restated it
    confusion   — non-degenerate but spurious-constraint pattern (target ∧ extra)
    structured  — non-degenerate and NOT confusion (genuine decomposition attempt)

The 'is_confusion' field is written by run_collect.py for runs after this feature landed.
For older runs without that field, confusion is detected from subgoal strings if the
run file also contains 'target_statement'. Falls back to 'unknown' if neither is present.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proving_ground.hardness import is_confusion_non_degenerate, is_trivial_tautology
from proving_ground.models import Decomposition, Subgoal


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


def _classify_entry(entry: dict, run_target: str | None) -> str:
    """Return 'degenerate', 'confusion', 'tautology', 'structured', or 'unknown'."""
    from proving_ground.hardness import is_degenerate as _is_degenerate

    def _make_decomp(target: str) -> Decomposition:
        return Decomposition(
            target_id="",
            target_statement=target,
            subgoals=tuple(Subgoal(id=str(i), statement=sg) for i, sg in enumerate(entry.get("subgoals", []))),
            root_implication_verified=False,
            statement_matches_target=False,
            axioms_clean=False,
        )

    if "is_degenerate" not in entry:
        # Pre-classifier format. No run_target → unknown.
        if run_target is None:
            return "unknown"
        decomp = _make_decomp(run_target)
        if _is_degenerate(decomp):
            return "degenerate"
        if is_trivial_tautology(decomp):
            return "tautology"
        return "confusion" if is_confusion_non_degenerate(decomp) else "structured"
    if entry["is_degenerate"]:
        return "degenerate"
    # For post-classifier runs: always recompute tautology from subgoal strings,
    # since it wasn't written to disk in older run files.
    if run_target is not None:
        decomp = _make_decomp(run_target)
        if is_trivial_tautology(decomp):
            return "tautology"
    if "is_confusion" in entry:
        return "confusion" if entry["is_confusion"] else "structured"
    if run_target is not None:
        decomp = _make_decomp(run_target)
        return "confusion" if is_confusion_non_degenerate(decomp) else "structured"
    return "unknown"


def compute_model_rates(runs: list[dict]) -> dict[str, dict]:
    """Return per-model stats with four-way classification."""
    stats: dict[str, dict] = {}
    for run in runs:
        run_target = run.get("target_statement")
        for entry in run.get("entries", []):
            model = entry["model"]
            if model not in stats:
                stats[model] = {
                    "attempts": 0,
                    "degenerate": 0,
                    "confusion": 0,
                    "tautology": 0,
                    "structured": 0,
                    "unknown_nondegen": 0,
                }
            stats[model]["attempts"] += 1
            label = _classify_entry(entry, run_target)
            if label == "degenerate":
                stats[model]["degenerate"] += 1
            elif label == "confusion":
                stats[model]["confusion"] += 1
            elif label == "tautology":
                stats[model]["tautology"] += 1
            elif label == "structured":
                stats[model]["structured"] += 1
            else:
                stats[model]["unknown_nondegen"] += 1
        for err in run.get("errors", []):
            model = err["model"]
            if model not in stats:
                stats[model] = {
                    "attempts": 0,
                    "degenerate": 0,
                    "confusion": 0,
                    "tautology": 0,
                    "structured": 0,
                    "unknown_nondegen": 0,
                }
    for model, s in stats.items():
        n = s["attempts"]
        s["degeneracy_rate"] = s["degenerate"] / n if n > 0 else None
        non_degen = s["confusion"] + s["tautology"] + s["structured"] + s["unknown_nondegen"]
        s["non_degenerate"] = non_degen
        s["non_degenerate_rate"] = non_degen / n if n > 0 else None
        s["structured_rate"] = s["structured"] / n if n > 0 else None
    return stats


def print_rates(problem_id: str, runs: list[dict], stats: dict[str, dict], three_way: bool = False) -> None:
    n_runs = len(runs)
    files = [r["_file"] for r in runs]
    print(f"\n{'='*70}")
    print(f"Problem: {problem_id}  ({n_runs} run{'s' if n_runs != 1 else ''})")
    print(f"Files: {', '.join(files)}")
    print(f"{'='*70}")
    if three_way:
        print(f"{'Model':<30} {'N':>4} {'Deg':>5} {'Conf':>5} {'Taut':>5} {'Struct':>7} {'Unk':>4} {'DegRate':>8} {'95% CI':>14}")
        print(f"{'-'*30} {'-'*4} {'-'*5} {'-'*5} {'-'*5} {'-'*7} {'-'*4} {'-'*8} {'-'*14}")
        for model, s in sorted(stats.items()):
            n = s["attempts"]
            deg_rate = f"{s['degeneracy_rate']:.0%}" if s['degeneracy_rate'] is not None else "N/A"
            if n > 0:
                lo, hi = wilson_ci(s["degenerate"], n)
                ci = f"[{lo:.0%}, {hi:.0%}]"
            else:
                ci = "N/A"
            print(
                f"{model:<30} {n:>4} {s['degenerate']:>5} {s['confusion']:>5}"
                f" {s.get('tautology', 0):>5} {s['structured']:>7} {s['unknown_nondegen']:>4} {deg_rate:>8} {ci:>14}"
            )
    else:
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
    """Print content of non-degenerate runs for manual structured/confusion review."""
    non_degen = []
    for run in runs:
        for entry in run.get("entries", []):
            if not entry["is_degenerate"]:
                label = entry.get("is_confusion")
                tag = "confusion" if label else ("structured" if label is False else "unknown")
                non_degen.append((run["_file"], entry["model"], tag, entry["subgoals"]))
    if not non_degen:
        return
    print(f"\n--- Non-degenerate outputs for {problem_id} ---")
    for fname, model, tag, subgoals in non_degen:
        print(f"  [{fname}] {model} ({tag}):")
        for sg in subgoals:
            print(f"    {sg}")


def print_comparison(
    problem_id: str,
    stats: dict[str, dict],
    cmp_id: str,
    cmp_stats: dict[str, dict],
    three_way: bool,
) -> None:
    print(f"\n{'='*70}")
    print(f"Comparison: {problem_id} vs {cmp_id}")
    if three_way:
        print(f"Hypothesis: {problem_id} should have HIGHER structured rate than {cmp_id}")
        print(f"(literature anchors → structured non-degeneracy over confusion)")
        print(f"{'='*70}")
        all_models = sorted(set(stats) | set(cmp_stats))
        for model in all_models:
            a = stats.get(model, {})
            b = cmp_stats.get(model, {})
            a_s = a.get("structured", 0)
            a_n = a.get("attempts", 0)
            b_s = b.get("structured", 0)
            b_n = b.get("attempts", 0)
            a_rate = a_s / a_n if a_n > 0 else None
            b_rate = b_s / b_n if b_n > 0 else None
            if a_rate is not None and b_rate is not None:
                direction = "✓" if a_rate >= b_rate else "✗"
                print(f"  {model}: struct_rate {problem_id}={a_rate:.0%} vs {cmp_id}={b_rate:.0%} {direction}")
            else:
                a_str = f"{a_rate:.0%}" if a_rate is not None else "N/A"
                b_str = f"{b_rate:.0%}" if b_rate is not None else "N/A"
                print(f"  {model}: {problem_id}={a_str} vs {cmp_id}={b_str} (insufficient data)")
    else:
        print(f"Hypothesis: {problem_id} should have LOWER degeneracy rate than {cmp_id}")
        print(f"(literature anchors → structured non-degeneracy)")
        print(f"{'='*70}")
        all_models = sorted(set(stats) | set(cmp_stats))
        for model in all_models:
            a = stats.get(model, {})
            b = cmp_stats.get(model, {})
            a_rate = a.get("degeneracy_rate")
            b_rate = b.get("degeneracy_rate")
            if a_rate is not None and b_rate is not None:
                direction = "✓" if a_rate <= b_rate else "✗"
                print(f"  {model}: {problem_id}={a_rate:.0%} vs {cmp_id}={b_rate:.0%} {direction}")
            else:
                print(f"  {model}: insufficient data")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--compare", help="Optional second problem to compare against")
    parser.add_argument("--runs-dir", default="runs/")
    parser.add_argument("--content", action="store_true", help="Show non-degenerate content")
    parser.add_argument("--three-way", action="store_true", help="Show degenerate/confusion/structured breakdown")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    runs = load_runs(args.problem_id, runs_dir)
    stats = compute_model_rates(runs)
    print_rates(args.problem_id, runs, stats, three_way=args.three_way)

    if args.content:
        print_non_degenerate_content(args.problem_id, runs)

    if args.compare:
        cmp_runs = load_runs(args.compare, runs_dir)
        cmp_stats = compute_model_rates(cmp_runs)
        print_rates(args.compare, cmp_runs, cmp_stats, three_way=args.three_way)

        if args.content:
            print_non_degenerate_content(args.compare, cmp_runs)

        print_comparison(args.problem_id, stats, args.compare, cmp_stats, args.three_way)


if __name__ == "__main__":
    main()
