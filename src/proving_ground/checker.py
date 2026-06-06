"""The Lean integration boundary.

The scorer in :mod:`proving_ground.scoring` consumes a :class:`~proving_ground.models.Decomposition`
whose verification flags are already set. *Setting* those flags truthfully is the
checker's job, and it is the only part of the system that must run inside a real Lean
toolchain (locally on the fleet, or in the Docker image under ``docker/``).

We keep this an abstract interface for two reasons:

1. The metric stays testable with no toolchain (see ``tests/test_scoring.py``).
2. The trust boundary is explicit. A checker must do all of: compile the submission,
   confirm the target statement is byte-identical to the frozen spec, audit axioms, and
   re-check through a fresh kernel. Anything less and "it compiled" gets mistaken for
   "it's proven" — the single most common way these benchmarks are fooled.

The concrete :class:`LeanInteractChecker` wraps ``leanprover-community/repl`` via the
``lean-interact`` package + ``SafeVerify`` for the anti-cheat gates. It imports its Lean
dependencies lazily so this module is importable everywhere; constructing it without a
toolchain raises a clear error rather than failing at import time.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass

from proving_ground.models import Decomposition, Subgoal
from proving_ground.scoring import STANDARD_AXIOMS


@dataclass(frozen=True)
class ProofArtifact:
    """A raw submission from a model, before any checking.

    Attributes:
        target_id: The open problem being addressed.
        target_statement: The frozen Lean statement of the target (the spec).
        lean_source: Full Lean source: the root implication proof plus each subgoal's
            statement and (where attempted) proof. Subgoals left open contain ``sorry``.
        subgoal_ids: Declared subgoal identifiers, in dependency order.
    """

    target_id: str
    target_statement: str
    lean_source: str
    subgoal_ids: tuple[str, ...]


class CheckerError(RuntimeError):
    """Raised when the checking environment itself is broken (not a failed proof)."""


class LeanChecker(ABC):
    """Turns a raw :class:`ProofArtifact` into a verified :class:`Decomposition`.

    Implementations MUST, for the result to be trustworthy:
      * compile the submission against the pinned mathlib;
      * set ``statement_matches_target`` only if the target's *type and value* are
        byte-identical to the frozen spec (SafeVerify gate C — blocks goal tampering);
      * set ``axioms_clean`` only if every discharged node depends solely on
        :data:`~proving_ground.scoring.STANDARD_AXIOMS` AND survives a fresh kernel
        re-check (``leanchecker --fresh`` / ``Environment.replay``);
      * set ``root_implication_verified`` only if ``(subgoals -> target)`` is kernel-proven;
      * mark a :class:`~proving_ground.models.Subgoal` ``discharged`` only if it has a
        complete, ``sorry``-free, axiom-clean, kernel-checked proof.
    """

    @abstractmethod
    def check(self, artifact: ProofArtifact) -> Decomposition:
        """Verify a submission and return a fully-populated Decomposition."""
        raise NotImplementedError


class LeanInteractChecker(LeanChecker):
    """Concrete checker over ``leanprover-community/repl`` + ``SafeVerify``.

    Requires a Lean toolchain (``lake``) and the ``lean-interact`` extra. Construction
    fails loudly if either is missing, so callers get a clear message instead of a
    mysterious mid-run failure.
    """

    def __init__(self, *, lean_version: str, mathlib_rev: str | None = None) -> None:
        if shutil.which("lake") is None:
            raise CheckerError(
                "No Lean toolchain found (`lake` not on PATH). Run the checker on a "
                "machine with Lean installed, or use the Docker image in docker/. The "
                "scoring metric itself needs no toolchain."
            )
        try:
            import lean_interact  # noqa: F401
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise CheckerError(
                "lean-interact is not installed. Install with: "
                'uv pip install -e ".[lean]"'
            ) from exc

        self.lean_version = lean_version
        self.mathlib_rev = mathlib_rev
        self._server = None  # lazily started AutoLeanServer

    # The full implementation is deferred to the Lean-integration milestone; the steps
    # are enumerated so the contract is unambiguous for whoever wires it (likely on ren4).
    def check(self, artifact: ProofArtifact) -> Decomposition:  # pragma: no cover
        raise NotImplementedError(
            "LeanInteractChecker.check is the next milestone (Lean-backed verification on "
            "the fleet). Contract:\n"
            "  1. Start an AutoLeanServer with a pickled `import Mathlib` env.\n"
            "  2. Compile artifact.lean_source; collect REPL messages + remaining sorries.\n"
            "  3. statement_matches_target := SafeVerify type+value match vs frozen spec.\n"
            "  4. For each subgoal: discharged := no error, not in remaining sorries,\n"
            "     `#print axioms` ⊆ STANDARD_AXIOMS, survives `leanchecker --fresh`.\n"
            "  5. root_implication_verified := (subgoals -> target) proof is sorry-free.\n"
            "  6. axioms_clean := every discharged node passes the axiom allowlist."
        )


class RecordingChecker(LeanChecker):
    """A test/offline double: returns a Decomposition from pre-recorded verdicts.

    Lets the harness and leaderboard be developed and tested end-to-end against fixed
    verdicts without a toolchain. NOT a verifier — it trusts whatever it's given.
    """

    def __init__(self, decomposition: Decomposition) -> None:
        self._decomposition = decomposition

    def check(self, artifact: ProofArtifact) -> Decomposition:
        return self._decomposition


def standard_axioms() -> frozenset[str]:
    """The canonical allowlist, re-exported for checker implementations."""
    return STANDARD_AXIOMS


__all__ = [
    "ProofArtifact",
    "CheckerError",
    "LeanChecker",
    "LeanInteractChecker",
    "RecordingChecker",
    "Subgoal",
    "standard_axioms",
]
