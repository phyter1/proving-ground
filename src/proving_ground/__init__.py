"""proving-ground: a benchmark for LLMs on provably unsolved problems.

The public surface is intentionally small. The novel, dependency-free part — the
scoring metric — lives in :mod:`proving_ground.scoring` and :mod:`proving_ground.models`
and runs anywhere, no Lean toolchain required. The Lean-backed checking lives behind the
interfaces in :mod:`proving_ground.checker`.
"""

from proving_ground.models import (
    Decomposition,
    Problem,
    RunResult,
    Score,
    ScoreKind,
    Subgoal,
    Tier,
)
from proving_ground.results import Leaderboard, ModelStanding, TierStats, aggregate
from proving_ground.scoring import STANDARD_AXIOMS, score_decomposition

__all__ = [
    "Decomposition",
    "Problem",
    "RunResult",
    "Score",
    "ScoreKind",
    "Subgoal",
    "Tier",
    "STANDARD_AXIOMS",
    "score_decomposition",
    "Leaderboard",
    "ModelStanding",
    "TierStats",
    "aggregate",
]

__version__ = "0.1.0"
