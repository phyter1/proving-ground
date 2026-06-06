"""The partial-credit metric. See docs/SCORING.md for the full rationale.

This module is pure and dependency-free on purpose: the novel contribution of the project
is this scoring logic, so it must be testable without a Lean toolchain. A checker
populates the verification flags on a :class:`Decomposition`; this turns them into a score.
"""

from __future__ import annotations

from proving_ground.models import Decomposition, Score, ScoreKind

# The only axioms a clean Lean proof may depend on. Anything else (sorryAx,
# Lean.trustCompiler from native_decide, user-declared axioms) means the proof is not
# trustworthy. The checker enforces this; we restate it here as the canonical set.
STANDARD_AXIOMS: frozenset[str] = frozenset(
    {"propext", "Classical.choice", "Quot.sound"}
)


def _fail(d: Decomposition, reason: str) -> Score:
    return Score(
        value=0.0,
        kind=ScoreKind.NONE,
        discharged_weight=d.discharged_weight,
        total_weight=d.total_weight,
        remaining_open_ids=tuple(sg.id for sg in d.remaining_open),
        rationale=reason,
    )


def score_decomposition(d: Decomposition) -> Score:
    """Score a submission against an open target.

    Hard gates first (any failure -> 0.0). Then continuous partial credit as the fraction
    of subgoal weight that has been kernel-discharged. See docs/SCORING.md.
    """
    # --- Hard gates: any failure scores exactly 0.0 -------------------------
    if not d.statement_matches_target:
        return _fail(
            d,
            "Statement integrity gate failed: submitted target does not match the "
            "frozen spec (possible goal tampering).",
        )
    if not d.axioms_clean:
        return _fail(
            d,
            "Axiom cleanliness gate failed: a discharged node depends on a non-standard "
            f"axiom (allowed: {sorted(STANDARD_AXIOMS)}). Possible sorry-laundering or "
            "native_decide exploit.",
        )
    if not d.root_implication_verified:
        return _fail(
            d,
            "Root implication gate failed: (subgoals -> target) is not kernel-verified. "
            "Without it the decomposition merely relocates the sorry — no progress.",
        )
    for sg in d.remaining_open:
        if sg.statement == d.target_statement:
            return _fail(
                d,
                f"Non-triviality gate failed: open subgoal {sg.id!r} is logically "
                "identical to the target (the null reduction 'C follows from C').",
            )

    # --- All gates passed: compute credit ----------------------------------
    remaining_ids = tuple(sg.id for sg in d.remaining_open)

    # No open subgoals left => a complete, kernel-verified proof of the target.
    if not remaining_ids:
        return Score(
            value=1.0,
            kind=ScoreKind.SOLVED,
            discharged_weight=d.discharged_weight,
            total_weight=d.total_weight,
            remaining_open_ids=(),
            rationale="Complete proof: all subgoals discharged and (subgoals -> target) "
            "verified.",
        )

    # Partial: verified reduction. Scalar = fraction of weight discharged. v1 awards no
    # scalar for an un-grounded reduction (discharged_weight == 0) — but the remaining
    # open lemmas are always surfaced as new benchmark problems.
    total = d.total_weight
    value = (d.discharged_weight / total) if total > 0 else 0.0
    value = max(0.0, min(1.0, value))

    return Score(
        value=value,
        kind=ScoreKind.REDUCTION,
        discharged_weight=d.discharged_weight,
        total_weight=total,
        remaining_open_ids=remaining_ids,
        rationale=(
            f"Verified reduction: {d.discharged_weight:g}/{total:g} subgoal weight "
            f"discharged; {len(remaining_ids)} open lemma(s) remain and re-enter the "
            "corpus as new problems."
        ),
    )
