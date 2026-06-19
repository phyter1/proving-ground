"""Core data model for the benchmark.

These types are deliberately pure data with no Lean dependency. A Lean-backed checker
(:mod:`proving_ground.checker`) is responsible for *populating* the verification flags
(``discharged``, ``root_implication_verified``, ``axioms_clean``, ...); the scorer in
:mod:`proving_ground.scoring` consumes them. Keeping the two apart means the metric — the
novel part — is testable without a toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(str, Enum):
    """Difficulty / contamination tier of a problem. See docs/SCORING.md."""

    SOLVED_RECENT = "solved_recent"  # known proof, post-cutoff — calibration + contamination canary
    WEAKLY_OPEN = "weakly_open"  # open to current provers, plausibly tractable
    OPEN = "open"  # genuinely open conjecture


class ScoreKind(str, Enum):
    """The qualitative outcome of a submission."""

    SOLVED = "solved"  # all subgoals discharged: a complete, kernel-verified proof
    REDUCTION = "reduction"  # partial: verified reduction with some subgoals discharged
    NONE = "none"  # no creditable progress (failed a hard gate or zero discharged)


@dataclass(frozen=True)
class Subgoal:
    """A single lemma in a proof decomposition.

    ``statement`` is the Lean type of the lemma. ``discharged`` is set True only by a
    checker that has kernel-verified a complete, axiom-clean proof of it. ``weight``
    expresses relative difficulty; problems may ship curated weights, otherwise uniform.
    """

    id: str
    statement: str
    weight: float = 1.0
    discharged: bool = False

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(f"subgoal {self.id!r} has negative weight {self.weight}")


@dataclass(frozen=True)
class Decomposition:
    """A submission against an open target.

    A model proposes that ``target`` follows from ``subgoals`` (the root implication),
    discharges some of them, and leaves the rest as explicit open lemmas. The boolean
    flags are verdicts produced by the checker, not claims trusted from the model.

    Attributes:
        target_id: Identifier of the open problem being addressed.
        target_statement: The frozen Lean statement of the target. Used for the
            non-triviality gate (no remaining subgoal may equal it).
        subgoals: The lemmas the target is reduced to.
        root_implication_verified: Kernel-verified that ``(subgoals) -> target``.
        statement_matches_target: SafeVerify gate C — submitted target type+value is
            byte-identical to the frozen spec (no goal tampering).
        axioms_clean: Every discharged node depends only on the standard axioms (no
            ``sorryAx``, no ``trustCompiler``, no user axioms) AND survives kernel replay.
    """

    target_id: str
    target_statement: str
    subgoals: tuple[Subgoal, ...] = field(default_factory=tuple)
    root_implication_verified: bool = False
    statement_matches_target: bool = False
    axioms_clean: bool = False

    @property
    def total_weight(self) -> float:
        return sum(sg.weight for sg in self.subgoals)

    @property
    def discharged_weight(self) -> float:
        return sum(sg.weight for sg in self.subgoals if sg.discharged)

    @property
    def remaining_open(self) -> tuple[Subgoal, ...]:
        """Subgoals still open — these become new benchmark problems."""
        return tuple(sg for sg in self.subgoals if not sg.discharged)


@dataclass(frozen=True)
class Score:
    """The result of scoring a submission. ``value`` is in [0, 1]."""

    value: float
    kind: ScoreKind
    discharged_weight: float
    total_weight: float
    remaining_open_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Problem:
    """A benchmark problem: an open (or recent-solved) statement to attack.

    This is the unit a model is asked to make progress on, and the unit a corpus source
    (formal-conjectures, SorryDB, or a remaining-open lemma fed back from a prior run)
    is normalized into.

    Attributes:
        id: Stable unique identifier.
        statement: The frozen Lean statement (the spec a submission must match).
        tier: Difficulty / contamination tier.
        source: Provenance, e.g. "formal-conjectures", "sorrydb", "self-renewed".
        title: Human-readable name.
        references: External links/citations (e.g. erdosproblems.com entry).
        preamble: Lean imports/opens/defs a submission may assume (e.g. "import Mathlib").
        proved_after: ISO date a known proof first existed (for contamination windowing
            of the solved_recent tier); None for genuinely open problems.
        metadata: Free-form extra fields from the source.
    """

    id: str
    statement: str
    tier: Tier
    source: str
    title: str = ""
    references: tuple[str, ...] = field(default_factory=tuple)
    preamble: str = "import Mathlib"
    proved_after: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    required_predicates: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunResult:
    """One model's scored attempt at one problem — the leaderboard's row.

    Attributes:
        model: Identifier of the model/system evaluated (e.g. "claude-opus-4-8",
            "fleet:ren4/qwen3.5:9b").
        problem_id: The Problem attempted.
        tier: The problem's tier (denormalized for per-tier aggregation).
        score: The Score the metric assigned.
        timestamp: ISO-8601 time the attempt was scored (caller-supplied; the harness
            does not invent clocks).
        artifact_ref: Optional pointer to the stored raw submission (path/URL/hash).
    """

    model: str
    problem_id: str
    tier: Tier
    score: Score
    timestamp: str
    artifact_ref: str | None = None
