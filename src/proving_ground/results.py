"""Aggregate :class:`RunResult` rows into a per-tier leaderboard.

A benchmark run emits one :class:`~proving_ground.models.RunResult` per (model, problem).
This module (de)serializes those rows and folds them into a :class:`Leaderboard` whose
standings are reported **strictly per tier**. docs/SCORING.md is emphatic that a single
blended number across ``solved_recent`` / ``weakly_open`` / ``open`` would be dishonest:
failing ``solved_recent`` means broken, moving ``weakly_open`` means real progress, and a
nonzero ``open`` score means a genuine contribution to mathematics. Those are not
commensurable, so we never average across them.

Pure data + stdlib only. No Lean, no third-party deps.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground.models import RunResult, Score, ScoreKind, Tier

# Stable tier ordering for reporting: calibration first, then where the gradient lives,
# then the headline frontier.
TIER_ORDER: tuple[Tier, ...] = (Tier.SOLVED_RECENT, Tier.WEAKLY_OPEN, Tier.OPEN)


# --- JSON (de)serialization ------------------------------------------------


def _score_to_dict(s: Score) -> dict:
    return {
        "value": s.value,
        "kind": s.kind.value,
        "discharged_weight": s.discharged_weight,
        "total_weight": s.total_weight,
        "remaining_open_ids": list(s.remaining_open_ids),
        "rationale": s.rationale,
    }


def _score_from_dict(d: dict) -> Score:
    return Score(
        value=float(d["value"]),
        kind=ScoreKind(d["kind"]),
        discharged_weight=float(d["discharged_weight"]),
        total_weight=float(d["total_weight"]),
        remaining_open_ids=tuple(d["remaining_open_ids"]),
        rationale=d["rationale"],
    )


def _result_to_dict(r: RunResult) -> dict:
    return {
        "model": r.model,
        "problem_id": r.problem_id,
        "tier": r.tier.value,
        "score": _score_to_dict(r.score),
        "timestamp": r.timestamp,
        "artifact_ref": r.artifact_ref,
    }


def _result_from_dict(d: dict) -> RunResult:
    return RunResult(
        model=d["model"],
        problem_id=d["problem_id"],
        tier=Tier(d["tier"]),
        score=_score_from_dict(d["score"]),
        timestamp=d["timestamp"],
        artifact_ref=d.get("artifact_ref"),
    )


def load_results(path: str | Path) -> list[RunResult]:
    """Load a list of :class:`RunResult` from a JSON file.

    The file is a JSON array of result objects with a nested ``score`` object and string
    enum values for ``tier`` / ``score.kind``.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"expected a JSON array of results, got {type(raw).__name__}")
    return [_result_from_dict(item) for item in raw]


def dump_results(results: list[RunResult], path: str | Path) -> None:
    """Serialize a list of :class:`RunResult` to a JSON file (pretty-printed)."""
    payload = [_result_to_dict(r) for r in results]
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# --- aggregation -----------------------------------------------------------


@dataclass(frozen=True)
class TierStats:
    """One model's aggregate performance within a single tier.

    Per docs/SCORING.md these are never blended across tiers — each tier carries its own
    meaning. ``open_lemmas_surfaced`` is the cumulative count of remaining open subgoals
    the model produced (the self-renewing engine's output), summed over its attempts.
    """

    attempted: int
    mean_score: float
    solved: int  # score == 1.0
    partial: int  # 0 < score < 1
    best_score: float
    open_lemmas_surfaced: int


@dataclass(frozen=True)
class ModelStanding:
    """One model's standings across every tier it attempted.

    ``per_tier`` maps a :class:`Tier` to that tier's :class:`TierStats`. A tier with no
    attempts is simply absent from the mapping.
    """

    model: str
    per_tier: dict[Tier, TierStats] = field(default_factory=dict)

    def stats(self, tier: Tier) -> TierStats | None:
        """The model's stats for ``tier``, or ``None`` if it did not attempt that tier."""
        return self.per_tier.get(tier)

    def open_contribution(self) -> bool:
        """True iff this model scored nonzero on the ``open`` tier — the headline fact.

        A nonzero ``open``-tier score is, per docs/SCORING.md, a genuine contribution to
        mathematics. This is what the leaderboard exists to surface.
        """
        st = self.per_tier.get(Tier.OPEN)
        return st is not None and st.best_score > 0.0


@dataclass(frozen=True)
class Leaderboard:
    """Aggregated standings for a benchmark run, grouped by model then tier."""

    standings: tuple[ModelStanding, ...]

    def tiers(self) -> list[Tier]:
        """Tiers that any model attempted, in canonical reporting order."""
        present = {t for s in self.standings for t in s.per_tier}
        return [t for t in TIER_ORDER if t in present]

    def rank(self, tier: Tier) -> list[ModelStanding]:
        """Models that attempted ``tier``, ranked by (solved desc, mean score desc).

        Ties broken by best score then model name for a stable, deterministic order.
        Models that did not attempt the tier are excluded.
        """
        entrants = [s for s in self.standings if tier in s.per_tier]

        def key(s: ModelStanding) -> tuple:
            st = s.per_tier[tier]
            return (-st.solved, -st.mean_score, -st.best_score, s.model)

        return sorted(entrants, key=key)

    def open_contributors(self) -> list[ModelStanding]:
        """Models with a nonzero ``open``-tier score, best-first — the headline."""
        return [s for s in self.rank(Tier.OPEN) if s.open_contribution()]


def _tier_stats(scores: list[Score]) -> TierStats:
    attempted = len(scores)
    values = [s.value for s in scores]
    mean = sum(values) / attempted if attempted else 0.0
    solved = sum(1 for v in values if v == 1.0)
    partial = sum(1 for v in values if 0.0 < v < 1.0)
    best = max(values) if values else 0.0
    surfaced = sum(len(s.remaining_open_ids) for s in scores)
    return TierStats(
        attempted=attempted,
        mean_score=mean,
        solved=solved,
        partial=partial,
        best_score=best,
        open_lemmas_surfaced=surfaced,
    )


def aggregate(results: list[RunResult]) -> Leaderboard:
    """Fold raw run results into a :class:`Leaderboard`.

    Results are grouped by (model, tier) — the tier on the :class:`RunResult` is
    authoritative (denormalized from the problem at scoring time). Within each group we
    compute the per-tier stats. We deliberately never aggregate across tiers.
    """
    grouped: dict[str, dict[Tier, list[Score]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        grouped[r.model][r.tier].append(r.score)

    standings: list[ModelStanding] = []
    for model in sorted(grouped):
        per_tier = {
            tier: _tier_stats(scores)
            for tier, scores in grouped[model].items()
        }
        standings.append(ModelStanding(model=model, per_tier=per_tier))

    return Leaderboard(standings=tuple(standings))
