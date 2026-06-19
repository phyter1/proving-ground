"""Tests for the cross-model agreement / hardness signal module."""

from __future__ import annotations

import pytest

from proving_ground.hardness import (
    ConsensusResult,
    _is_target_echo,
    _normalize_statement,
    _token_containment,
    compute_consensus,
    is_degenerate,
    novelty_weight,
    pairwise_jaccard,
)
from proving_ground.models import Decomposition, Subgoal

THEOREM = "∀ n : ℕ, Even n ∨ Odd n"


# --- helpers ----------------------------------------------------------------


def _decomp(target_id: str, statements: list[str], target_statement: str = "TARGET_GOAL") -> Decomposition:
    """Minimal Decomposition passing all hard gates."""
    return Decomposition(
        target_id=target_id,
        target_statement=target_statement,
        subgoals=tuple(Subgoal(f"L{i}", s) for i, s in enumerate(statements)),
        root_implication_verified=True,
        statement_matches_target=True,
        axioms_clean=True,
    )


# --- pairwise_jaccard -------------------------------------------------------


def test_identical_sets_returns_one():
    s = frozenset({"A", "B"})
    assert pairwise_jaccard([s, s, s]) == pytest.approx(1.0)


def test_disjoint_sets_returns_zero():
    a = frozenset({"A", "B"})
    b = frozenset({"C", "D"})
    assert pairwise_jaccard([a, b]) == pytest.approx(0.0)


def test_partial_overlap_two_sets():
    a = frozenset({"A", "B"})
    b = frozenset({"A", "C"})
    # intersection = {A}, union = {A, B, C}, jaccard = 1/3
    assert pairwise_jaccard([a, b]) == pytest.approx(1 / 3)


def test_single_set_returns_one():
    assert pairwise_jaccard([frozenset({"A", "B"})]) == pytest.approx(1.0)


def test_empty_list_returns_one():
    assert pairwise_jaccard([]) == pytest.approx(1.0)


def test_both_empty_sets_return_one():
    assert pairwise_jaccard([frozenset(), frozenset()]) == pytest.approx(1.0)


def test_three_sets_mean_of_three_pairs():
    a = frozenset({"A"})
    b = frozenset({"B"})
    c = frozenset({"A"})
    # pairs: (a,b)=0, (a,c)=1, (b,c)=0 → mean = 1/3
    assert pairwise_jaccard([a, b, c]) == pytest.approx(1 / 3)


def test_one_empty_one_nonempty():
    a = frozenset()
    b = frozenset({"A"})
    # union = {A}, intersection = {} → 0
    assert pairwise_jaccard([a, b]) == pytest.approx(0.0)


# --- is_degenerate ----------------------------------------------------------


def test_sole_subgoal_equals_target_is_degenerate():
    d = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    assert is_degenerate(d) is True


def test_sole_subgoal_equals_target_with_whitespace_is_degenerate():
    d = _decomp("conj-1", [f"  {THEOREM}  "], target_statement=THEOREM)
    assert is_degenerate(d) is True


def test_sole_subgoal_differs_is_not_degenerate():
    d = _decomp("conj-1", ["Even 0 ∨ Odd 0"], target_statement=THEOREM)
    assert is_degenerate(d) is False


def test_multiple_subgoals_not_degenerate_even_if_one_matches():
    # Two subgoals: not a degenerate echo regardless of content
    d = _decomp("conj-1", [THEOREM, "Even 0 ∨ Odd 0"], target_statement=THEOREM)
    assert is_degenerate(d) is False


def test_empty_subgoals_not_degenerate():
    d = _decomp("conj-1", [], target_statement=THEOREM)
    assert is_degenerate(d) is False


def test_near_degenerate_quantifier_weakening():
    # Observed: qwen3.5 dropped the ∀ N wrapper from twin primes conjecture.
    # All tokens in the subgoal appear in the full target → containment 1.0.
    target = "∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)"
    subgoal = "∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"
    d = _decomp("twin-primes", [subgoal], target_statement=target)
    assert is_degenerate(d) is True


def test_near_degenerate_low_containment_not_flagged():
    # A genuine single-step decomposition introduces a lemma name not in the target.
    target = "∀ n : ℕ, Even n ∨ Odd n"
    subgoal = "apply Nat.even_or_odd"
    d = _decomp("conj-1", [subgoal], target_statement=target)
    assert is_degenerate(d) is False


def test_near_degenerate_multi_subgoal_not_flagged():
    # Near-degenerate check only applies to single-subgoal decompositions.
    target = "∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)"
    subgoal_a = "∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"
    subgoal_b = "N < p"
    d = _decomp("twin-primes", [subgoal_a, subgoal_b], target_statement=target)
    assert is_degenerate(d) is False


def test_all_subgoals_target_echo_multi_is_degenerate():
    # Observed in calibration: gemma4 produced ["Even (n*(n+1))", "Even (n*(n+1))"]
    # where the target was "∀ n : ℕ, Even (n*(n+1))". Both subgoals normalize to
    # the target — the model filled two slots but made no real decomposition.
    target = "∀ n : ℕ, Even (n * (n + 1))"
    d = _decomp("even-product", ["Even (n * (n + 1))", "Even (n * (n + 1))"], target_statement=target)
    assert is_degenerate(d) is True


def test_all_subgoals_exact_echo_multi_is_degenerate():
    # Same theorem repeated verbatim across three slots.
    d = _decomp("conj-1", [THEOREM, THEOREM, THEOREM], target_statement=THEOREM)
    assert is_degenerate(d) is True


def test_partial_echo_multi_not_degenerate():
    # One echo + one real (low-containment) subgoal → not degenerate.
    # "Even 0 ∨ Odd 0" is a specific instance but its token-containment with
    # "∀ n : ℕ, Even n ∨ Odd n" is ~0.75 (below the 0.9 threshold).
    d = _decomp("conj-1", [THEOREM, "Even 0 ∨ Odd 0"], target_statement=THEOREM)
    assert is_degenerate(d) is False



# --- _token_containment -----------------------------------------------------


def test_token_containment_exact_subset():
    # All subgoal tokens appear in target → 1.0
    assert _token_containment("∃ p Nat.Prime", "∀ N ∃ p Nat.Prime N < p") == pytest.approx(1.0)


def test_token_containment_no_overlap():
    assert _token_containment("apply simp rfl", "∀ N ∃ p Nat.Prime") == pytest.approx(0.0)


def test_token_containment_empty_subgoal():
    assert _token_containment("", "∀ N ∃ p") == pytest.approx(1.0)


# --- _is_target_echo --------------------------------------------------------


def test_is_target_echo_exact_match():
    assert _is_target_echo(THEOREM, THEOREM) is True


def test_is_target_echo_normalized_match():
    # Dropping the ∀ wrapper still echoes the target.
    assert _is_target_echo("Even n ∨ Odd n", "∀ n : ℕ, Even n ∨ Odd n") is True


def test_is_target_echo_near_degenerate_containment_not_flagged():
    # _is_target_echo does NOT use token containment (unlike is_degenerate).
    # A near-degenerate weakening of the target is not caught here — only exact
    # and normalized-exact matches are filtered to avoid false positives on
    # short lemma statements that legitimately share tokens with longer targets.
    target = "∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)"
    subgoal = "∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"
    assert _is_target_echo(subgoal, target) is False


def test_is_target_echo_genuine_subgoal_not_flagged():
    # A real lemma introduces novel vocabulary.
    assert _is_target_echo("Even 0 ∨ Odd 0", THEOREM) is False
    assert _is_target_echo("∀ n m : ℕ, Odd (n + m) → Even n ∨ Even m", THEOREM) is False


# --- compute_consensus ------------------------------------------------------


def test_identical_decompositions_zero_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "B"])
    r = compute_consensus("conj-1", [d1, d2])
    assert isinstance(r, ConsensusResult)
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert r.n_models == 2
    assert r.n_degenerate == 0
    assert r.problem_id == "conj-1"


def test_disjoint_decompositions_full_hardness():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["C", "D"])
    r = compute_consensus("conj-1", [d1, d2])
    assert r.hardness_score == pytest.approx(1.0)
    assert r.n_degenerate == 0


def test_novel_statements_first_model_all_novel():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "C"])
    r = compute_consensus("conj-1", [d1, d2])
    # A is in d1 first, B is in d1, C is in d2 but not d1
    assert {"A", "B", "C"} == r.novel_statements


def test_single_decomposition_hardness_none():
    # Only one real model: cross-model agreement is undefined, not "trivially tractable".
    d = _decomp("conj-1", ["A", "B"])
    r = compute_consensus("conj-1", [d])
    assert r.consensus_score is None
    assert r.hardness_score is None
    assert r.n_models == 1
    assert r.n_degenerate == 0
    # Novel statements are still populated from the one real model.
    assert "A" in r.novel_statements
    assert "B" in r.novel_statements


def test_empty_decompositions_raises():
    with pytest.raises(ValueError):
        compute_consensus("conj-1", [])


def test_empty_subgoal_sets_high_consensus():
    # Both models produced no lemmas — trivially identical
    d1 = _decomp("conj-1", [])
    d2 = _decomp("conj-1", [])
    r = compute_consensus("conj-1", [d1, d2])
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
    assert r.novel_statements == frozenset()
    assert r.n_degenerate == 0


def test_three_model_partial_overlap():
    d1 = _decomp("conj-1", ["A", "B"])
    d2 = _decomp("conj-1", ["A", "C"])
    d3 = _decomp("conj-1", ["D", "E"])
    # pairs: (d1,d2): |{A}|/|{A,B,C}|=1/3, (d1,d3): 0/4=0, (d2,d3): 0/4=0
    # mean = (1/3 + 0 + 0) / 3 = 1/9
    r = compute_consensus("conj-1", [d1, d2, d3])
    assert r.consensus_score == pytest.approx(1 / 9)
    assert r.hardness_score == pytest.approx(8 / 9)
    assert r.n_degenerate == 0


def test_all_degenerate_consensus_is_none():
    # Reproduces the beat 655 failure: Qwen3.5 echoed the theorem statement
    d1 = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    d2 = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    r = compute_consensus("conj-1", [d1, d2])
    assert r.consensus_score is None
    assert r.hardness_score is None
    assert r.n_models == 2
    assert r.n_degenerate == 2
    assert r.novel_statements == frozenset()


def test_mixed_degenerate_single_real_hardness_none():
    # One degenerate (Qwen3.5-style echo), one real (Gemma4-style inductive decomp).
    # With only one real decomposition, cross-model agreement is undefined.
    echo = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    real = _decomp("conj-1", ["Even 0 ∨ Odd 0", "Even (S k) ∨ Odd (S k)"], target_statement=THEOREM)
    r = compute_consensus("conj-1", [echo, real])
    assert r.n_models == 2
    assert r.n_degenerate == 1
    assert r.consensus_score is None
    assert r.hardness_score is None
    # Novel statements still populated from the one real model.
    assert "Even 0 ∨ Odd 0" in r.novel_statements
    assert "Even (S k) ∨ Odd (S k)" in r.novel_statements


def test_mixed_degenerate_two_real_models_computes_correctly():
    # Degenerate + two real models with partial overlap
    echo = _decomp("conj-1", [THEOREM], target_statement=THEOREM)
    d1 = _decomp("conj-1", ["A", "B"], target_statement=THEOREM)
    d2 = _decomp("conj-1", ["A", "C"], target_statement=THEOREM)
    r = compute_consensus("conj-1", [echo, d1, d2])
    assert r.n_models == 3
    assert r.n_degenerate == 1
    # pairwise_jaccard([{A,B},{A,C}]) = 1/3
    assert r.consensus_score == pytest.approx(1 / 3)
    assert r.hardness_score == pytest.approx(2 / 3)


def test_near_degenerate_filtered_leaves_one_real_returns_none():
    # Observed twin-primes pattern: qwen3.5 near-degenerate, gemma4 real.
    # After filtering: N_real=1 → consensus/hardness undefined.
    target = "∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)"
    near_degen = _decomp("twin-primes", ["∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"], target_statement=target)
    real = _decomp("twin-primes", ["N < p", "Nat.Prime (p + 2)"], target_statement=target)
    r = compute_consensus("twin-primes", [near_degen, real])
    assert r.n_models == 2
    assert r.n_degenerate == 1
    assert r.consensus_score is None
    assert r.hardness_score is None
    assert "N < p" in r.novel_statements
    assert "Nat.Prime (p + 2)" in r.novel_statements


def test_multi_subgoal_with_target_echo_filters_echo():
    # Observed: Granite produced [target_echo, real_subgoal].
    # The target echo must be removed from statement sets before consensus.
    # Remaining: 1 degenerate (Qwen echo) + 1 real after filtering (Granite).
    # Only 1 real decomposition → consensus undefined.
    granite = _decomp(
        "conj-1",
        [THEOREM, "∀ n m : ℕ, Odd (n + m) → Even n ∨ Even m"],
        target_statement=THEOREM,
    )
    qwen = _decomp("conj-1", [THEOREM], target_statement=THEOREM)  # classic degenerate
    r = compute_consensus("conj-1", [qwen, granite])
    assert r.n_degenerate == 1  # only qwen (single-subgoal echo) is degenerate
    assert r.consensus_score is None  # only 1 real model after filtering granite's echo
    assert r.hardness_score is None
    # Target echo must NOT appear as novel
    assert THEOREM not in r.novel_statements
    # Granite's real subgoal IS novel
    assert "∀ n m : ℕ, Odd (n + m) → Even n ∨ Even m" in r.novel_statements


def test_multi_subgoal_target_echo_filtered_before_jaccard():
    # Two non-degenerate models each include the target alongside distinct real subgoals.
    # After filtering the echo, their real subgoals are disjoint → hardness=1.
    d1 = _decomp("conj-1", [THEOREM, "Even 0 ∨ Odd 0"], target_statement=THEOREM)
    d2 = _decomp("conj-1", [THEOREM, "Even (S k) ∨ Odd (S k)"], target_statement=THEOREM)
    r = compute_consensus("conj-1", [d1, d2])
    assert r.n_degenerate == 0  # both have 2 subgoals, is_degenerate returns False
    assert r.consensus_score == pytest.approx(0.0)  # real subgoals fully disjoint
    assert r.hardness_score == pytest.approx(1.0)
    assert THEOREM not in r.novel_statements
    assert "Even 0 ∨ Odd 0" in r.novel_statements
    assert "Even (S k) ∨ Odd (S k)" in r.novel_statements


# --- novelty_weight ---------------------------------------------------------


def test_seen_statement_zero_weight():
    seen = frozenset({"A", "B"})
    assert novelty_weight("A", seen, hardness_score=0.8) == pytest.approx(0.0)
    assert novelty_weight("B", seen, hardness_score=0.5) == pytest.approx(0.0)


def test_novel_statement_scaled_by_hardness():
    seen = frozenset({"A"})
    assert novelty_weight("C", seen, hardness_score=0.7) == pytest.approx(0.7)
    assert novelty_weight("D", seen, hardness_score=1.0) == pytest.approx(1.0)


def test_novel_statement_zero_hardness_zero_weight():
    # Trivially obvious problem (all models agreed) → new lemma still earns 0
    seen = frozenset()
    assert novelty_weight("A", seen, hardness_score=0.0) == pytest.approx(0.0)


def test_empty_seen_any_statement_novel():
    assert novelty_weight("X", frozenset(), hardness_score=0.6) == pytest.approx(0.6)


# --- _normalize_statement ----------------------------------------------------


def test_normalize_strips_single_forall():
    assert _normalize_statement("∀ n : ℕ, n + 0 = n") == "n + 0 = n"


def test_normalize_strips_multi_var_forall():
    assert _normalize_statement("∀ n m : ℕ, n + m = m + n") == "n + m = m + n"


def test_normalize_strips_chained_foralls():
    assert _normalize_statement("∀ n : ℕ, ∀ m : ℕ, n + m = m + n") == "n + m = m + n"


def test_normalize_leaves_existential_unchanged():
    stmt = "∃ p : ℕ, Nat.Prime p ∧ Nat.Prime (p + 2)"
    assert _normalize_statement(stmt) == stmt


def test_normalize_leaves_bare_statement_unchanged():
    stmt = "n + 0 = n"
    assert _normalize_statement(stmt) == stmt


def test_normalize_nonempty_result_after_strip():
    # Should not return empty string even for a bare quantifier edge case.
    result = _normalize_statement("∀ n : ℕ, True")
    assert result  # non-empty


# --- quantifier-normalized consensus -----------------------------------------


def test_forall_stripped_models_reach_consensus():
    """∀-prefixed and bare forms of the same statement count as identical for Jaccard."""
    target = "∀ n : ℕ, n + 0 = n"
    d1 = _decomp("add-id", ["∀ n : ℕ, n + 0 = n", "∀ n : ℕ, 0 + n = n"], target_statement=target)
    d2 = _decomp("add-id", ["n + 0 = n", "0 + n = n"], target_statement=target)
    r = compute_consensus("add-id", [d1, d2])
    # Neither is degenerate (both have 2 subgoals).
    assert r.n_degenerate == 0
    # After normalization, both models produce the same two statements → Jaccard = 1.0
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)


def test_forall_normalized_degenerate_detection():
    """Subgoal equal to target after quantifier stripping is degenerate."""
    target = "∀ n : ℕ, n + 0 = n"
    d = _decomp("add-id", ["n + 0 = n"], target_statement=target)
    assert is_degenerate(d) is True


def test_forall_normalized_degenerate_does_not_affect_multi_subgoal():
    """Quantifier stripping degenerate check still only fires on single-subgoal decomps."""
    target = "∀ n : ℕ, n + 0 = n"
    d = _decomp("add-id", ["n + 0 = n", "0 + n = n"], target_statement=target)
    assert is_degenerate(d) is False


# --- known limitations (xfail) -----------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Alpha-equivalence normalization not implemented. "
        "_normalize_statement strips ∀ prefixes but does not rename bound variables "
        "in the body. Two models writing the same proof step with different variable "
        "name conventions (e.g. b,k vs n,m) produce disjoint token sets and get "
        "Jaccard=0 when the correct answer is ~1.0. Fix requires parsing bound "
        "variable names from the stripped prefix and renaming by first-appearance "
        "order in the body."
    ),
)
def test_alpha_equivalent_subgoals_reach_consensus():
    """Models agreeing on proof structure but differing only in variable names should score consensus=1.0.

    After ∀-stripping: 'k + b = b + k' vs 'n + m = m + n' are alpha-equivalent
    (same structure, different variable names) but currently score Jaccard=0.
    This inflates hardness_score for problems where all models find the same path.
    """
    target = "∀ n : ℕ, n + 0 = n"
    d1 = _decomp(
        "comm",
        ["∀ b k : ℕ, k + b = b + k", "∀ b : ℕ, b + 0 = 0 + b"],
        target_statement=target,
    )
    d2 = _decomp(
        "comm",
        ["∀ n m : ℕ, n + m = m + n", "∀ n : ℕ, n + 0 = 0 + n"],
        target_statement=target,
    )
    r = compute_consensus("comm", [d1, d2])
    assert r.n_degenerate == 0
    assert r.consensus_score == pytest.approx(1.0)
    assert r.hardness_score == pytest.approx(0.0)
