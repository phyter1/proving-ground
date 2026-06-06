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

    def check(self, artifact: ProofArtifact) -> Decomposition:  # pragma: no cover
        """Verify a submission against a live Lean toolchain.

        The orchestration here is real and final: gather raw outputs from the toolchain,
        then hand them to the tested, pure decision logic in :mod:`proving_ground.lean_checker`
        (which carries the trust rules and is unit-tested without a toolchain). Only the
        three toolchain-bound leaves below remain — they shell out to repl / Lean /
        SafeVerify and are implemented in the Lean-integration milestone (runs on ren4 or
        in the Docker image under ``docker/``).
        """
        from proving_ground.lean_checker import derive_decomposition, parse_repl_response

        # 1. Confirm the target statement was not tampered with (SafeVerify gate C).
        statement_matches = self._safe_verify_statement(artifact)

        # 2. Check the root implication (subgoals -> target) and each subgoal node.
        root_repl = parse_repl_response(self._run_repl(artifact.lean_source, node="root"))
        root_axioms = self._print_axioms(artifact, node="root")

        subgoal_specs: list[tuple[str, str, float]] = []
        subgoal_repls = {}
        subgoal_axioms = {}
        for sg_id in artifact.subgoal_ids:
            subgoal_specs.append((sg_id, self._statement_of(artifact, sg_id), 1.0))
            subgoal_repls[sg_id] = parse_repl_response(
                self._run_repl(artifact.lean_source, node=sg_id)
            )
            subgoal_axioms[sg_id] = self._print_axioms(artifact, node=sg_id)

        # 3. Assemble the verdict via the tested decision logic.
        return derive_decomposition(
            target_id=artifact.target_id,
            target_statement=artifact.target_statement,
            subgoal_specs=subgoal_specs,
            root_repl=root_repl,
            subgoal_repls=subgoal_repls,
            subgoal_axioms=subgoal_axioms,
            statement_matches_target=statement_matches,
            root_axioms=root_axioms,
        )

    # --- toolchain-bound leaves (next milestone; need a live Lean) --------------
    def _run_repl(self, lean_source: str, *, node: str) -> dict:  # pragma: no cover
        raise NotImplementedError(
            "Start an AutoLeanServer with a pickled `import Mathlib` env, submit the "
            "source, and return the raw repl JSON (messages + sorries + env)."
        )

    def _print_axioms(self, artifact: ProofArtifact, *, node: str) -> frozenset[str]:  # pragma: no cover  # noqa: E501
        raise NotImplementedError(
            "Run `#print axioms <node>` and `leanchecker --fresh`, return the axiom set."
        )

    def _safe_verify_statement(self, artifact: ProofArtifact) -> bool:  # pragma: no cover
        raise NotImplementedError(
            "Run SafeVerify to confirm the submitted target type+value is byte-identical "
            "to the frozen spec (blocks goal tampering)."
        )

    def _statement_of(self, artifact: ProofArtifact, subgoal_id: str) -> str:  # pragma: no cover  # noqa: E501
        raise NotImplementedError(
            "Extract the declared Lean type of the given subgoal from the submission."
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
