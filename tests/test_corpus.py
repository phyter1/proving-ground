"""Tests for the corpus adapters and the self-renewing engine.

These cover the three ingestion paths (formal-conjectures Lean source, SorryDB JSON,
self-renewal from a verified reduction), plus dedup and JSON round-tripping.
"""

from __future__ import annotations

from proving_ground import Decomposition, Problem, Subgoal, Tier
from proving_ground.corpus import (
    dedup,
    load_corpus,
    parse_formal_conjecture,
    parse_sorrydb,
    renew_from_decomposition,
    save_corpus,
)

# --- parse_formal_conjecture -----------------------------------------------

def test_open_theorem_with_by_sorry():
    src = "theorem foo (n : Nat) : n + 0 = n := by sorry"
    problems = parse_formal_conjecture(src)
    assert len(problems) == 1
    p = problems[0]
    assert p.tier is Tier.OPEN
    assert p.title == "foo"
    assert p.statement == "n + 0 = n"
    assert p.source == "formal-conjectures"
    assert p.id == "formal-conjectures::foo"


def test_open_theorem_with_bare_sorry():
    src = "theorem bar : 2 + 2 = 4 := sorry"
    problems = parse_formal_conjecture(src)
    assert len(problems) == 1
    assert problems[0].tier is Tier.OPEN
    assert problems[0].statement == "2 + 2 = 4"


def test_real_proof_is_solved_recent():
    src = "theorem add_zero (n : Nat) : n + 0 = n := by simp"
    problems = parse_formal_conjecture(src)
    assert len(problems) == 1
    assert problems[0].tier is Tier.SOLVED_RECENT
    assert problems[0].title == "add_zero"


def test_formal_proof_attribute_is_solved_even_without_proof_text():
    # @[formal_proof] marks a registered proof: solved even if body shape looks sparse.
    src = "@[formal_proof]\ntheorem solved_one : True := trivial"
    problems = parse_formal_conjecture(src)
    assert len(problems) == 1
    assert problems[0].tier is Tier.SOLVED_RECENT


def test_references_pulled_from_comment_url():
    src = (
        "-- See https://www.erdosproblems.com/123 for context.\n"
        "theorem erdos_123 : 1 = 1 := by sorry"
    )
    problems = parse_formal_conjecture(src)
    assert len(problems) == 1
    assert problems[0].references == ("https://www.erdosproblems.com/123",)


def test_multiple_declarations_in_one_source():
    src = (
        "import Mathlib\n"
        "theorem first : P := by sorry\n"
        "theorem second : Q := by simp\n"
        "lemma third : R := sorry\n"
    )
    problems = parse_formal_conjecture(src)
    assert [p.title for p in problems] == ["first", "second", "third"]
    assert [p.tier for p in problems] == [Tier.OPEN, Tier.SOLVED_RECENT, Tier.OPEN]
    # All share the discovered preamble.
    assert all(p.preamble == "import Mathlib" for p in problems)


def test_preamble_defaults_when_no_imports():
    src = "theorem no_imports : P := by sorry"
    problems = parse_formal_conjecture(src)
    assert problems[0].preamble == "import Mathlib"


def test_custom_source_label():
    src = "theorem x : P := by sorry"
    problems = parse_formal_conjecture(src, source="custom-set")
    assert problems[0].source == "custom-set"
    assert problems[0].id == "custom-set::x"


# --- parse_sorrydb ---------------------------------------------------------

def test_sorrydb_basic_records():
    records = [
        {"id": "abc123", "goal": "P → Q", "repo": "https://github.com/x/y", "file": "A.lean"},
        {"id": "def456", "statement": "n = n"},
    ]
    problems = parse_sorrydb(records)
    assert len(problems) == 2
    assert all(p.tier is Tier.OPEN for p in problems)
    assert all(p.source == "sorrydb" for p in problems)
    assert problems[0].id == "sorrydb::abc123"
    assert problems[0].statement == "P → Q"
    assert problems[0].metadata["repo"] == "https://github.com/x/y"
    assert problems[0].metadata["file"] == "A.lean"
    assert problems[0].references == ("https://github.com/x/y",)
    assert problems[1].id == "sorrydb::def456"


def test_sorrydb_missing_id_gets_hashed_id():
    records = [{"goal": "some open statement"}]
    problems = parse_sorrydb(records)
    assert len(problems) == 1
    assert problems[0].id.startswith("sorrydb::")
    # Deterministic: same statement -> same hashed id.
    again = parse_sorrydb([{"goal": "some open statement"}])
    assert problems[0].id == again[0].id


def test_sorrydb_missing_statement_is_skipped():
    records = [{"id": "no-goal-here", "repo": "r"}, {"goal": "real"}]
    problems = parse_sorrydb(records)
    assert len(problems) == 1
    assert problems[0].statement == "real"


# --- renew_from_decomposition ----------------------------------------------

def _verified_decomp(*, root: bool) -> Decomposition:
    return Decomposition(
        target_id="conj-1",
        target_statement="C",
        subgoals=(
            Subgoal("L1", "lemma one", discharged=True),  # discharged -> not renewed
            Subgoal("L2", "lemma two"),  # open -> renewed
            Subgoal("L3", "lemma three"),  # open -> renewed
        ),
        root_implication_verified=root,
        statement_matches_target=True,
        axioms_clean=True,
    )


def test_renew_emits_open_subgoals_as_problems():
    decomp = _verified_decomp(root=True)
    problems = renew_from_decomposition(decomp, parent_problem_id="parent-1")
    assert len(problems) == 2
    ids = {p.id for p in problems}
    assert ids == {"parent-1::L2", "parent-1::L3"}
    statements = {p.statement for p in problems}
    assert statements == {"lemma two", "lemma three"}
    for p in problems:
        assert p.source == "self-renewed"
        assert p.tier is Tier.WEAKLY_OPEN
        assert p.metadata["parent_problem_id"] == "parent-1"
        assert p.metadata["parent_target_id"] == "conj-1"


def test_renew_returns_empty_without_verified_root_implication():
    decomp = _verified_decomp(root=False)
    assert renew_from_decomposition(decomp, parent_problem_id="parent-1") == []


def test_renew_custom_tier():
    decomp = _verified_decomp(root=True)
    problems = renew_from_decomposition(decomp, parent_problem_id="p", tier=Tier.OPEN)
    assert all(p.tier is Tier.OPEN for p in problems)


# --- dedup -----------------------------------------------------------------

def test_dedup_removes_whitespace_variants():
    problems = [
        Problem(id="a", statement="P  →   Q", tier=Tier.OPEN, source="s"),
        Problem(id="b", statement="P → Q", tier=Tier.OPEN, source="s"),
        Problem(id="c", statement="P\n→\tQ", tier=Tier.OPEN, source="s"),
        Problem(id="d", statement="R", tier=Tier.OPEN, source="s"),
    ]
    out = dedup(problems)
    assert [p.id for p in out] == ["a", "d"]  # first whitespace-variant kept


def test_dedup_empty():
    assert dedup([]) == []


# --- save/load round-trip --------------------------------------------------

def test_corpus_round_trip(tmp_path):
    problems = [
        Problem(
            id="formal-conjectures::foo",
            statement="n + 0 = n",
            tier=Tier.OPEN,
            source="formal-conjectures",
            title="foo",
            references=("https://example.com/1", "https://example.com/2"),
            preamble="import Mathlib\nimport Foo",
            proved_after=None,
        ),
        Problem(
            id="sorrydb::abc",
            statement="P → Q",
            tier=Tier.SOLVED_RECENT,
            source="sorrydb",
            proved_after="2026-01-01",
            metadata={"repo": "r", "file": "A.lean"},
        ),
    ]
    path = tmp_path / "corpus.json"
    save_corpus(problems, path)
    loaded = load_corpus(path)
    assert loaded == problems
