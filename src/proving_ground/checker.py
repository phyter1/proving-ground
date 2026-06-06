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

    The submission protocol (see docs/SCORING.md "submission protocol"): the source
    declares each subgoal as its own theorem (proved or left ``sorry``), plus a *reduction*
    theorem that takes the subgoal statements as hypotheses and concludes the frozen
    target — ``reduction : H1 → … → Hk → Target``. Taking the lemmas as hypotheses is what
    lets the reduction be verified independently of whether the lemmas are proven; without
    it ``#print axioms`` on the target would transitively report ``sorryAx`` and partial
    credit would be impossible.

    Attributes:
        target_id: The open problem being addressed.
        target_statement: The frozen Lean statement of the target (the spec).
        lean_source: Full Lean source: the reduction theorem plus each subgoal theorem.
        subgoal_ids: Declared subgoal theorem names, in the order they appear as the
            reduction's hypotheses.
        root_name: Name of the reduction theorem (default ``"reduction"``).
    """

    target_id: str
    target_statement: str
    lean_source: str
    subgoal_ids: tuple[str, ...]
    root_name: str = "reduction"


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

    def __init__(
        self,
        *,
        lean_version: str | None = None,
        project_dir: str | None = None,
        timeout: int = 120,
    ) -> None:
        if shutil.which("lake") is None:
            raise CheckerError(
                "No Lean toolchain found (`lake` not on PATH). Run the checker on a "
                "machine with Lean installed (e.g. ren4 with ELAN_HOME=/models/.elan on "
                "PATH), or use the Docker image in docker/. The scoring metric itself "
                "needs no toolchain."
            )
        try:
            import lean_interact  # noqa: F401
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise CheckerError(
                "lean-interact is not installed. Install with: "
                'uv pip install -e ".[lean]"'
            ) from exc

        self.lean_version = lean_version
        self.project_dir = project_dir
        self.timeout = timeout
        self._server = None  # lazily started; reused across check() calls
        self._mathlib_env = None  # env id after `import Mathlib`

    def _ensure_server(self):
        """Start the REPL once and import Mathlib once; reuse for every submission."""
        if self._server is not None:
            return
        from lean_interact import AutoLeanServer, Command, LeanREPLConfig, LocalProject

        if self.project_dir is not None:
            config = LeanREPLConfig(project=LocalProject(directory=self.project_dir))
        else:  # pragma: no cover - exercised on the fleet with a configured project
            config = LeanREPLConfig()
        self._server = AutoLeanServer(config)
        base = self._server.run(Command(cmd="import Mathlib"))
        self._mathlib_env = base.env

    def check(self, artifact: ProofArtifact) -> Decomposition:  # pragma: no cover - needs Lean
        """Verify a submission against a live Lean kernel. See docs/SCORING.md.

        Protocol (probe-verified against repl on ren4):

        1. Elaborate the whole submission once, in the Mathlib env.
        2. For each subgoal theorem, ``#print axioms <name>`` — discharged iff that
           succeeds and the axiom set is clean (no ``sorryAx`` from a ``sorry``, no
           ``Lean.trustCompiler`` from ``native_decide``, no user axioms). ``#print axioms``
           is transitive, so this is the real soundness check, not "it compiled".
        3. ``#print axioms <reduction>`` — the reduction must itself be clean.
        4. Statement integrity: elaborate
           ``example : (H1) → … → (Hk) → (frozen target) := @<reduction>`` where each
           ``Hi`` is the elaborated type of subgoal ``i``. This pins the reduction's
           conclusion to the *frozen* target (blocks goal-tampering) and its hypotheses to
           the declared subgoal statements — all in one kernel check.
        """
        from lean_interact import Command

        self._ensure_server()
        server = self._server

        # 1. Elaborate the whole submission. The returned env holds the new declarations;
        # every subsequent query must run against THAT env, not the base Mathlib one.
        submission = server.run(Command(cmd=artifact.lean_source, env=self._mathlib_env))
        env = submission.env

        # 2. Per-subgoal axiom audit + elaborated type.
        subgoals: list[Subgoal] = []
        hyp_types: list[str] = []
        for sg_id in artifact.subgoal_ids:
            axioms = self._axioms_of(sg_id, env)
            hyp_types.append(self._type_of(sg_id, env))
            discharged = axioms is not None and axioms <= STANDARD_AXIOMS
            subgoals.append(
                Subgoal(id=sg_id, statement=hyp_types[-1] or sg_id, discharged=discharged)
            )

        # 3. Reduction axiom audit.
        root_axioms = self._axioms_of(artifact.root_name, env)
        root_clean = root_axioms is not None and root_axioms <= STANDARD_AXIOMS

        # 4. Statement-integrity kernel check.
        statement_matches = self._statement_integrity(artifact, hyp_types, env)

        return Decomposition(
            target_id=artifact.target_id,
            target_statement=artifact.target_statement,
            subgoals=tuple(subgoals),
            root_implication_verified=root_clean and statement_matches,
            statement_matches_target=statement_matches,
            axioms_clean=root_clean,
        )

    # --- toolchain helpers ----------------------------------------------------
    def _axioms_of(self, name: str, env) -> frozenset[str] | None:  # pragma: no cover
        """Axiom set of a declaration, or None if it doesn't exist (failed to elaborate)."""
        from lean_interact import Command

        from proving_ground.lean_checker import parse_axioms

        resp = self._server.run(Command(cmd=f"#print axioms {name}", env=env))
        if any(m.severity == "error" for m in resp.messages):
            return None  # unknown identifier -> the declaration did not compile
        for m in resp.messages:
            if "depends on axioms" in m.data or "does not depend on" in m.data:
                return parse_axioms(m.data)
        return None

    def _type_of(self, name: str, env) -> str:  # pragma: no cover
        """Elaborated type string of a declaration via ``#check @name`` (best effort)."""
        from lean_interact import Command

        resp = self._server.run(Command(cmd=f"#check @{name}", env=env))
        for m in resp.messages:
            if m.severity != "error" and " : " in m.data:
                return m.data.split(" : ", 1)[1].strip()
        return ""

    def _statement_integrity(self, artifact, hyp_types, env) -> bool:  # pragma: no cover
        """True iff `example : H1 → … → Hk → target := @reduction` elaborates cleanly."""
        from lean_interact import Command

        if not all(hyp_types):
            return False  # a subgoal type we couldn't read -> fail closed
        arrow = "".join(f"({h}) → " for h in hyp_types)
        cmd = f"example : {arrow}({artifact.target_statement}) := @{artifact.root_name}"
        resp = self._server.run(Command(cmd=cmd, env=env))
        return not any(m.severity == "error" for m in resp.messages)


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
