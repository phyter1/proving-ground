"""Unit tests for the pure verification logic in :mod:`proving_ground.lean_checker`.

All fixtures are CANNED — hand-written REPL JSON and ``#print axioms`` strings. No Lean
toolchain, no network. The end-to-end assertions route the derived Decomposition through
:func:`proving_ground.scoring.score_decomposition` to confirm the verdict the metric
actually produces.
"""

from __future__ import annotations

from proving_ground.lean_checker import (
    NodeCheck,
    axioms_clean,
    derive_decomposition,
    parse_axioms,
    parse_repl_response,
)
from proving_ground.models import ScoreKind
from proving_ground.scoring import STANDARD_AXIOMS, score_decomposition

# ---------------------------------------------------------------------------
# Canned REPL JSON shapes
# ---------------------------------------------------------------------------

CLEAN_REPL = {"env": 1}

CLEAN_REPL_EMPTY_MESSAGES = {"messages": [], "sorries": [], "env": 7}

SORRY_REPL = {
    "sorries": [
        {
            "pos": {"line": 3, "column": 2},
            "endPos": {"line": 3, "column": 7},
            "goal": "⊢ True",
            "proofState": 0,
        }
    ],
    "messages": [
        {
            "severity": "warning",
            "pos": {"line": 3, "column": 0},
            "endPos": {"line": 3, "column": 7},
            "data": "declaration uses 'sorry'",
        }
    ],
    "env": 2,
}

ERROR_REPL = {
    "messages": [
        {
            "severity": "error",
            "pos": {"line": 5, "column": 0},
            "endPos": {"line": 5, "column": 4},
            "data": "unknown identifier 'foo'",
        },
        {
            "severity": "info",
            "pos": {"line": 1, "column": 0},
            "endPos": None,
            "data": "some info message",
        },
    ],
    "env": 3,
}


# ---------------------------------------------------------------------------
# Canned `#print axioms` strings
# ---------------------------------------------------------------------------

AX_CLEAN_3 = "'foo' depends on axioms: [propext, Classical.choice, Quot.sound]"
AX_NONE = "'foo' does not depend on any axioms"
AX_SORRY = "'foo' depends on axioms: [propext, sorryAx]"
AX_TRUST_COMPILER = "'foo' depends on axioms: [Lean.trustCompiler, Lean.ofReduceBool]"
AX_USER = "'foo' depends on axioms: [propext, myUnprovenAxiom]"


# ---------------------------------------------------------------------------
# parse_repl_response
# ---------------------------------------------------------------------------


def test_clean_proof_parses_to_no_errors() -> None:
    result = parse_repl_response(CLEAN_REPL)
    assert result.errors == ()
    assert result.sorries == ()
    assert result.env == 1
    assert result.compiled_clean is True
    assert result.fully_closed is True


def test_clean_proof_with_explicit_empty_lists() -> None:
    result = parse_repl_response(CLEAN_REPL_EMPTY_MESSAGES)
    assert result.errors == ()
    assert result.sorries == ()
    assert result.env == 7
    assert result.fully_closed is True


def test_sorry_shows_up_in_sorries_and_means_not_closed() -> None:
    result = parse_repl_response(SORRY_REPL)
    # The sorry warning is NOT an error — "it compiled" is not "it's proven".
    assert result.errors == ()
    assert result.compiled_clean is True
    # But a goal remains open, so it is not fully closed.
    assert result.sorries == ("⊢ True",)
    assert result.fully_closed is False


def test_error_messages_extracted_only_for_error_severity() -> None:
    result = parse_repl_response(ERROR_REPL)
    assert result.errors == ("unknown identifier 'foo'",)
    assert result.compiled_clean is False
    assert result.fully_closed is False


def test_empty_dict_parses_clean() -> None:
    result = parse_repl_response({})
    assert result.errors == ()
    assert result.sorries == ()
    assert result.env is None
    assert result.fully_closed is True


def test_malformed_entries_tolerated_without_dropping_open_goals() -> None:
    raw = {
        "messages": [{"severity": "error"}],  # no data
        "sorries": [{"proofState": 0}],  # no goal
    }
    result = parse_repl_response(raw)
    assert result.errors == ("",)  # error still counted
    assert result.sorries == ("",)  # sorry still counted (goal not lost)
    assert result.fully_closed is False


# ---------------------------------------------------------------------------
# parse_axioms
# ---------------------------------------------------------------------------


def test_parse_axioms_clean_three() -> None:
    assert parse_axioms(AX_CLEAN_3) == frozenset(
        {"propext", "Classical.choice", "Quot.sound"}
    )


def test_parse_axioms_no_axioms() -> None:
    assert parse_axioms(AX_NONE) == frozenset()


def test_parse_axioms_sorry() -> None:
    assert parse_axioms(AX_SORRY) == frozenset({"propext", "sorryAx"})


def test_parse_axioms_trust_compiler() -> None:
    assert parse_axioms(AX_TRUST_COMPILER) == frozenset(
        {"Lean.trustCompiler", "Lean.ofReduceBool"}
    )


def test_parse_axioms_user_axiom() -> None:
    assert parse_axioms(AX_USER) == frozenset({"propext", "myUnprovenAxiom"})


def test_parse_axioms_unrecognized_returns_empty() -> None:
    assert parse_axioms("totally unexpected output") == frozenset()


def test_parse_axioms_tolerates_whitespace_and_trailing_comma() -> None:
    raw = "'foo' depends on axioms: [propext ,  Classical.choice , ]"
    assert parse_axioms(raw) == frozenset({"propext", "Classical.choice"})


# ---------------------------------------------------------------------------
# axioms_clean
# ---------------------------------------------------------------------------


def test_axioms_clean_accepts_standard_set() -> None:
    assert axioms_clean(STANDARD_AXIOMS) is True


def test_axioms_clean_accepts_subset_and_empty() -> None:
    assert axioms_clean(frozenset()) is True
    assert axioms_clean(frozenset({"propext"})) is True


def test_axioms_clean_rejects_sorry_ax() -> None:
    assert axioms_clean(frozenset({"propext", "sorryAx"})) is False


def test_axioms_clean_rejects_trust_compiler() -> None:
    assert axioms_clean(frozenset({"Lean.trustCompiler"})) is False


def test_axioms_clean_rejects_user_axiom() -> None:
    assert axioms_clean(frozenset({"myUnprovenAxiom"})) is False


# ---------------------------------------------------------------------------
# NodeCheck
# ---------------------------------------------------------------------------


def test_nodecheck_verified_requires_all_three() -> None:
    clean = parse_repl_response(CLEAN_REPL)
    assert NodeCheck(repl=clean, axioms=STANDARD_AXIOMS).verified is True
    # Compiles clean but dirty axioms -> not verified.
    assert NodeCheck(repl=clean, axioms=frozenset({"sorryAx"})).verified is False
    # Clean axioms but a remaining sorry -> not verified.
    sorry = parse_repl_response(SORRY_REPL)
    assert NodeCheck(repl=sorry, axioms=STANDARD_AXIOMS).verified is False


# ---------------------------------------------------------------------------
# derive_decomposition + end-to-end scoring
# ---------------------------------------------------------------------------

TARGET_ID = "erdos_123"
TARGET_STMT = "theorem C : SomeOpenConjecture := by ..."

ROOT_CLEAN = parse_repl_response(CLEAN_REPL)


def _specs() -> list[tuple[str, str, float]]:
    return [("L1", "lemma L1 : P1", 1.0), ("L2", "lemma L2 : P2", 1.0)]


def test_fully_discharged_scores_one() -> None:
    repls = {
        "L1": parse_repl_response(CLEAN_REPL),
        "L2": parse_repl_response(CLEAN_REPL),
    }
    axioms = {"L1": STANDARD_AXIOMS, "L2": STANDARD_AXIOMS}
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls=repls,
        subgoal_axioms=axioms,
        statement_matches_target=True,
        root_axioms=STANDARD_AXIOMS,
    )
    assert all(sg.discharged for sg in decomp.subgoals)
    assert decomp.root_implication_verified is True
    assert decomp.axioms_clean is True

    score = score_decomposition(decomp)
    assert score.value == 1.0
    assert score.kind is ScoreKind.SOLVED


def test_half_discharged_scores_half() -> None:
    repls = {
        "L1": parse_repl_response(CLEAN_REPL),
        "L2": parse_repl_response(SORRY_REPL),  # left open
    }
    axioms = {"L1": STANDARD_AXIOMS, "L2": frozenset({"sorryAx"})}  # open => sorryAx ok
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls=repls,
        subgoal_axioms=axioms,
        statement_matches_target=True,
        root_axioms=STANDARD_AXIOMS,
    )
    discharged = {sg.id: sg.discharged for sg in decomp.subgoals}
    assert discharged == {"L1": True, "L2": False}
    # Open subgoal's dirty axioms must NOT poison the Decomposition-level flag.
    assert decomp.axioms_clean is True
    assert decomp.root_implication_verified is True

    score = score_decomposition(decomp)
    assert score.value == 0.5
    assert score.kind is ScoreKind.REDUCTION
    assert score.remaining_open_ids == ("L2",)


def test_compiles_but_dirty_axioms_is_not_discharged() -> None:
    # L2 "compiled clean" (no errors, no sorries) but depends on sorryAx — laundered.
    repls = {
        "L1": parse_repl_response(CLEAN_REPL),
        "L2": parse_repl_response(CLEAN_REPL),
    }
    axioms = {"L1": STANDARD_AXIOMS, "L2": frozenset({"propext", "sorryAx"})}
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls=repls,
        subgoal_axioms=axioms,
        statement_matches_target=True,
        root_axioms=STANDARD_AXIOMS,
    )
    discharged = {sg.id: sg.discharged for sg in decomp.subgoals}
    assert discharged == {"L1": True, "L2": False}
    # L2 is not discharged, so its dirty axioms don't appear among discharged nodes.
    assert decomp.axioms_clean is True

    score = score_decomposition(decomp)
    assert score.value == 0.5  # only L1 counts
    assert score.kind is ScoreKind.REDUCTION


def test_root_with_sorry_is_not_verified_and_scores_zero() -> None:
    repls = {
        "L1": parse_repl_response(CLEAN_REPL),
        "L2": parse_repl_response(CLEAN_REPL),
    }
    axioms = {"L1": STANDARD_AXIOMS, "L2": STANDARD_AXIOMS}
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=parse_repl_response(SORRY_REPL),  # root implication left open
        subgoal_repls=repls,
        subgoal_axioms=axioms,
        statement_matches_target=True,
        root_axioms=STANDARD_AXIOMS,
    )
    assert decomp.root_implication_verified is False
    # Hard gate: no verified root implication -> score 0.0.
    score = score_decomposition(decomp)
    assert score.value == 0.0
    assert score.kind is ScoreKind.NONE


def test_root_with_dirty_axioms_is_not_verified() -> None:
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls={
            "L1": parse_repl_response(CLEAN_REPL),
            "L2": parse_repl_response(CLEAN_REPL),
        },
        subgoal_axioms={"L1": STANDARD_AXIOMS, "L2": STANDARD_AXIOMS},
        statement_matches_target=True,
        root_axioms=frozenset({"Lean.trustCompiler"}),  # native_decide exploit on root
    )
    assert decomp.root_implication_verified is False
    assert decomp.axioms_clean is False
    assert score_decomposition(decomp).value == 0.0


def test_missing_subgoal_result_is_not_discharged() -> None:
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls={"L1": parse_repl_response(CLEAN_REPL)},  # L2 missing
        subgoal_axioms={"L1": STANDARD_AXIOMS},  # L2 missing
        statement_matches_target=True,
        root_axioms=STANDARD_AXIOMS,
    )
    discharged = {sg.id: sg.discharged for sg in decomp.subgoals}
    assert discharged == {"L1": True, "L2": False}
    assert score_decomposition(decomp).value == 0.5


def test_statement_mismatch_propagates_and_scores_zero() -> None:
    decomp = derive_decomposition(
        target_id=TARGET_ID,
        target_statement=TARGET_STMT,
        subgoal_specs=_specs(),
        root_repl=ROOT_CLEAN,
        subgoal_repls={
            "L1": parse_repl_response(CLEAN_REPL),
            "L2": parse_repl_response(CLEAN_REPL),
        },
        subgoal_axioms={"L1": STANDARD_AXIOMS, "L2": STANDARD_AXIOMS},
        statement_matches_target=False,  # SafeVerify gate C failed
        root_axioms=STANDARD_AXIOMS,
    )
    assert decomp.statement_matches_target is False
    # Even though everything else is verified, the integrity gate fails -> 0.0.
    assert score_decomposition(decomp).value == 0.0
