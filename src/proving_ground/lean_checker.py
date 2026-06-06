"""Pure verification logic for turning raw Lean-checking output into verdicts.

This module is the *decision layer* of the checker. It contains no subprocess, no REPL,
no network, and no Lean toolchain dependency — only the parsing of canned output shapes
and the rules that turn them into the boolean verdicts a
:class:`~proving_ground.models.Decomposition` carries.

That split is deliberate. The plumbing (starting an ``AutoLeanServer``, shelling out to
``leanchecker``, etc.) is mechanical and will be wired in a later milestone; *this* part —
"given what Lean said, is the proof actually trustworthy?" — is where the subtle,
benchmark-fooling bugs live. So it is isolated here as pure functions that can be unit
tested exhaustively against fixtures.

The governing principle, restated from docs/SCORING.md and checker.py: **"it compiled"
is not "it's proven."** The Lean elaborator will happily accept a file full of ``sorry``
and emit only *warnings*. A node is trustworthy only when ALL of:

* it produced no elaboration *errors*,
* it left no remaining ``sorry`` goals,
* and ``#print axioms`` on it stays within the standard allowlist.

The axiom audit is what catches the laundering: a proof can compile clean yet depend on
``sorryAx`` (a ``sorry`` smuggled through a helper lemma) or on ``Lean.trustCompiler`` /
``Lean.ofReduceBool`` (``native_decide`` exploits that route around the kernel — genuine
soundness holes). None of those show up as errors; only the axiom set reveals them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from proving_ground.models import Decomposition, Subgoal
from proving_ground.scoring import STANDARD_AXIOMS

__all__ = [
    "ReplResult",
    "NodeCheck",
    "parse_repl_response",
    "parse_axioms",
    "axioms_clean",
    "derive_decomposition",
]


@dataclass(frozen=True)
class ReplResult:
    """Parsed result of one ``leanprover-community/repl`` check.

    Attributes:
        errors: ``data`` strings of every message whose ``severity == "error"``. A proof
            compiled clean iff this is empty. Warnings (including the ``declaration uses
            'sorry'`` warning) are intentionally *not* errors — see module docstring.
        sorries: The ``goal`` string of each remaining ``sorry``. A specific goal is
            considered closed iff there are no errors AND it is not among these.
        env: The REPL environment id (used to thread state across commands), or ``None``
            if the response carried no ``env`` field.
    """

    errors: tuple[str, ...] = ()
    sorries: tuple[str, ...] = ()
    env: int | None = None

    @property
    def compiled_clean(self) -> bool:
        """True iff the REPL reported no errors. NOT sufficient for 'proven'."""
        return not self.errors

    @property
    def fully_closed(self) -> bool:
        """True iff no errors AND no remaining sorries (all goals discharged)."""
        return not self.errors and not self.sorries


@dataclass(frozen=True)
class NodeCheck:
    """Everything known about one node (a subgoal or the root) after checking.

    Bundles the REPL result with the audited axiom set so the discharge decision is made
    in one place from one record, rather than juggling parallel collections.

    Attributes:
        repl: The parsed REPL result for this node.
        axioms: The axiom set reported by ``#print axioms`` for this node.
    """

    repl: ReplResult
    axioms: frozenset[str]

    @property
    def verified(self) -> bool:
        """A node is verified iff it fully closed (no errors, no sorries) AND its axioms
        are within the standard allowlist.

        All three conditions are required: errors mean it did not elaborate; a remaining
        sorry means a goal is still open; dirty axioms mean the proof is untrustworthy
        even though it "compiled" (sorry-laundering or a native_decide soundness hole).
        """
        return self.repl.fully_closed and axioms_clean(self.axioms)


def parse_repl_response(raw: dict) -> ReplResult:
    """Parse the JSON object returned by ``leanprover-community/repl``.

    The REPL returns a dict with optional keys:

    * ``messages``: list of ``{severity, pos, endPos, data}``. We keep only the ``data``
      of messages with ``severity == "error"``. Warnings (notably the
      ``declaration uses 'sorry'`` warning) are deliberately ignored here — Lean reports
      ``sorry`` as a *warning*, not an error, which is exactly why "it compiled" cannot be
      trusted on its own and why we also inspect ``sorries`` and the axiom set.
    * ``sorries``: list of ``{pos, endPos, goal, proofState}``. We keep each ``goal``
      string; a non-empty list means goals remain open.
    * ``env``: integer environment id, or absent.

    Missing keys are treated as empty, so a bare ``{}`` (clean, nothing to report) parses
    to a clean result. Malformed message/sorry entries are tolerated defensively: a
    message with no ``data`` contributes an empty string, a sorry with no ``goal``
    contributes an empty string — we never want a parse glitch to silently turn an open
    goal into a closed one.
    """
    messages = raw.get("messages") or []
    errors = tuple(
        str(m.get("data", "")) for m in messages if m.get("severity") == "error"
    )

    sorries_raw = raw.get("sorries") or []
    sorries = tuple(str(s.get("goal", "")) for s in sorries_raw)

    env_val = raw.get("env")
    env = int(env_val) if isinstance(env_val, int) else None

    return ReplResult(errors=errors, sorries=sorries, env=env)


# Matches the bracketed axiom list in:
#   'foo' depends on axioms: [propext, Classical.choice, Quot.sound]
_AXIOM_LIST_RE = re.compile(r"depends on axioms:\s*\[(?P<body>.*?)\]", re.DOTALL)
# Matches the explicit no-axioms form:
#   'foo' does not depend on any axioms
_NO_AXIOMS_RE = re.compile(r"does not depend on any axioms")


def parse_axioms(print_axioms_output: str) -> frozenset[str]:
    """Parse the output of Lean's ``#print axioms foo``.

    Recognized shapes:

    * ``'foo' depends on axioms: [propext, Classical.choice, Quot.sound]`` -> the named
      set. The same shape carries the dangerous ones (``sorryAx``, ``Lean.trustCompiler``,
      ``Lean.ofReduceBool``); we extract them verbatim so :func:`axioms_clean` can reject.
    * ``'foo' does not depend on any axioms`` -> the empty set.

    Returns the set of axiom names. Whitespace and trailing commas are tolerated. Anything
    we cannot parse yields the empty set ONLY when it explicitly says "does not depend";
    an unrecognized non-empty string yields the empty set too — but note the caller's
    discharge logic never trusts an empty axiom set on its own to mean "clean and proven":
    a node is only verified when its REPL result also fully closed. We err toward parsing
    leniently here and gating strictly in :func:`derive_decomposition`.
    """
    if _NO_AXIOMS_RE.search(print_axioms_output):
        return frozenset()

    match = _AXIOM_LIST_RE.search(print_axioms_output)
    if not match:
        return frozenset()

    body = match.group("body")
    names = {tok.strip() for tok in body.split(",")}
    names.discard("")
    return frozenset(names)


def axioms_clean(axioms: frozenset[str]) -> bool:
    """True iff ``axioms`` is a subset of :data:`STANDARD_AXIOMS`.

    The allowlist is ``{propext, Classical.choice, Quot.sound}``. Any extra axiom fails:

    * ``sorryAx`` — a ``sorry`` laundered through this declaration or a dependency. The
      proof compiled (sorry is only a warning) but is logically vacuous.
    * ``Lean.trustCompiler`` / ``Lean.ofReduceBool`` — introduced by ``native_decide``,
      which trusts compiled native code instead of the kernel. That is a soundness hole
      and has been used to "prove" false statements; it must never count as clean.
    * any user-declared ``axiom`` — an unproven assumption the model slipped in.

    The empty set is clean (it is a subset of everything), but cleanliness alone is not
    proof — the caller must also confirm the node fully closed.
    """
    return axioms <= STANDARD_AXIOMS


def derive_decomposition(
    *,
    target_id: str,
    target_statement: str,
    subgoal_specs: list[tuple[str, str, float]],
    root_repl: ReplResult,
    subgoal_repls: dict[str, ReplResult],
    subgoal_axioms: dict[str, frozenset[str]],
    statement_matches_target: bool,
    root_axioms: frozenset[str],
) -> Decomposition:
    """Assemble a :class:`Decomposition` from per-node checking results.

    This is the trust boundary. Every flag set here is a verdict, never a model's claim,
    and the rule everywhere is: **when in doubt, mark NOT verified.**

    Args:
        target_id: Identifier of the open problem.
        target_statement: Frozen Lean statement of the target (passed through to the
            Decomposition for the downstream non-triviality gate).
        subgoal_specs: ``(id, statement, weight)`` for each declared subgoal, in order.
        root_repl: REPL result for the root implication ``(subgoals -> target)``.
        subgoal_repls: REPL result per subgoal id. A missing id is treated as a node that
            never checked -> NOT discharged.
        subgoal_axioms: ``#print axioms`` set per subgoal id. A missing id is treated as
            unknown -> NOT clean -> NOT discharged.
        statement_matches_target: SafeVerify gate C verdict (target type+value is
            byte-identical to the frozen spec). Passed straight through.
        root_axioms: ``#print axioms`` set for the root implication.

    Discharge / verification rules:

    * A subgoal is ``discharged`` iff its REPL result fully closed (no errors, no
      remaining sorries) AND its axioms are clean. A subgoal that "compiles" with dirty
      axioms (e.g. ``sorryAx``) is explicitly NOT discharged — that is the whole point of
      the axiom audit.
    * ``root_implication_verified`` iff the root REPL fully closed AND root axioms clean.
      A root with a remaining ``sorry`` is not verified — the reduction's logical link is
      unproven, so the decomposition merely relocates the sorry.
    * ``axioms_clean`` (the Decomposition-level flag) iff the root is clean AND every
      DISCHARGED subgoal is clean. We only audit discharged nodes because open subgoals
      legitimately contain ``sorry`` (and thus ``sorryAx``); their axioms are irrelevant
      to the credit. By construction every discharged node is already clean, so this is
      effectively ``root clean``, but we compute it explicitly so the invariant is
      checked rather than assumed.
    """
    subgoals: list[Subgoal] = []
    discharged_clean = True  # tracks: are all discharged nodes axiom-clean?

    for sg_id, statement, weight in subgoal_specs:
        repl = subgoal_repls.get(sg_id)
        axioms = subgoal_axioms.get(sg_id)

        # A node we have no result for cannot be trusted. Default: not discharged.
        if repl is None or axioms is None:
            discharged = False
        else:
            node = NodeCheck(repl=repl, axioms=axioms)
            discharged = node.verified
            # By construction a discharged node is clean; assert the invariant anyway.
            if discharged and not axioms_clean(axioms):
                discharged_clean = False

        subgoals.append(
            Subgoal(id=sg_id, statement=statement, weight=weight, discharged=discharged)
        )

    root_clean = axioms_clean(root_axioms)
    root_verified = root_repl.fully_closed and root_clean

    decomposition_axioms_clean = root_clean and discharged_clean

    return Decomposition(
        target_id=target_id,
        target_statement=target_statement,
        subgoals=tuple(subgoals),
        root_implication_verified=root_verified,
        statement_matches_target=statement_matches_target,
        axioms_clean=decomposition_axioms_clean,
    )
