"""Tests for the cross-model agreement / hardness signal module."""

from __future__ import annotations

import pytest

from proving_ground.hardness import (
    ConsensusResult,
    _extract_top_level_conjuncts,
    _is_target_echo,
    _normalize_statement,
    _token_containment,
    compute_consensus,
    is_confusion_non_degenerate,
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



# --- is_confusion_non_degenerate --------------------------------------------

LEGENDRE = "∀ n : ℕ, 0 < n → ∃ p : ℕ, n ^ 2 < p ∧ p < (n + 1) ^ 2 ∧ Nat.Prime p"
COLLATZ = "∀ n : ℕ, 0 < n → ∃ k : ℕ, Function.iterate (fun m => if m % 2 = 0 then m / 2 else 3 * m + 1) k n = 1"


def test_spurious_conjunct_is_confusion():
    # gpt-oss-20b pattern on Legendre: target ∧ p % 2 = 1
    subgoal = LEGENDRE + " ∧ p % 2 = 1"
    d = _decomp("legendre", [subgoal], target_statement=LEGENDRE)
    assert is_degenerate(d) is False
    assert is_confusion_non_degenerate(d) is True


def test_spurious_conjunct_collatz_is_confusion():
    # gpt-oss-20b pattern on Collatz: target ∧ k ≤ 100
    subgoal = COLLATZ + " ∧ k ≤ 100"
    d = _decomp("collatz", [subgoal], target_statement=COLLATZ)
    assert is_degenerate(d) is False
    assert is_confusion_non_degenerate(d) is True


def test_genuine_decomp_not_confusion():
    # gemma4 v1 Legendre: existence-in-interval + primality (two separate subgoals)
    d = _decomp(
        "legendre",
        ["∃ p : ℕ, n ^ 2 < p ∧ p < (n + 1) ^ 2", "Nat.Prime p"],
        target_statement=LEGENDRE,
    )
    assert is_degenerate(d) is False
    assert is_confusion_non_degenerate(d) is False


def test_degenerate_not_confusion():
    # Degenerate (exact echo) → is_confusion returns False by contract
    d = _decomp("legendre", [LEGENDRE], target_statement=LEGENDRE)
    assert is_degenerate(d) is True
    assert is_confusion_non_degenerate(d) is False


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


# --- is_trivial_tautology ---------------------------------------------------

from proving_ground.hardness import is_reference_only, is_trivial_tautology

TWIN_PRIMES = "∀ N : ℕ, ∃ p : ℕ, N < p ∧ Nat.Prime p ∧ Nat.Prime (p + 2)"


def test_trivial_tautology_true_subgoal():
    # gemma4-e4b pattern on twin-primes: sole subgoal is "True"
    d = _decomp("twin-primes", ["True"], target_statement=TWIN_PRIMES)
    assert is_trivial_tautology(d) is True


def test_trivial_tautology_top_subgoal():
    # Lean 4 ⊤ syntax variant
    d = _decomp("twin-primes", ["⊤"], target_statement=TWIN_PRIMES)
    assert is_trivial_tautology(d) is True


def test_trivial_tautology_not_degenerate():
    # Degenerate (restatement) → is_trivial_tautology returns False
    d = _decomp("twin-primes", [TWIN_PRIMES], target_statement=TWIN_PRIMES)
    assert is_degenerate(d) is True
    assert is_trivial_tautology(d) is False


def test_trivial_tautology_genuine_subgoal_not_flagged():
    # A non-tautology subgoal should not be flagged
    d = _decomp("twin-primes", ["∃ p, N < p ∧ Nat.Prime p"], target_statement=TWIN_PRIMES)
    assert is_trivial_tautology(d) is False


def test_trivial_tautology_mixed_subgoals_not_flagged():
    # If any subgoal is not a tautology, not flagged
    d = _decomp("twin-primes", ["True", "∃ p, Nat.Prime p"], target_statement=TWIN_PRIMES)
    assert is_trivial_tautology(d) is False


# --- is_reference_only -------------------------------------------------------

GOLDBACH = "∀ n : ℕ, 2 < n → Even n → ∃ p q : ℕ, Nat.Prime p ∧ Nat.Prime q ∧ p + q = n"


def test_reference_only_bare_lemma_id():
    # gemma4-e4b-mlx on Goldbach: sole subgoal is the identifier 'lemma_3'
    d = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    assert is_reference_only(d) is True


def test_reference_only_short_hypothesis():
    # 'h1' — a bare hypothesis name, not a proposition
    d = _decomp("goldbach", ["h1"], target_statement=GOLDBACH)
    assert is_reference_only(d) is True


def test_reference_only_all_identifiers():
    # All subgoals are bare identifiers
    d = _decomp("goldbach", ["lemma_3", "h1"], target_statement=GOLDBACH)
    assert is_reference_only(d) is True


def test_reference_only_mixed_identifier_and_proposition():
    # At least one real proposition → not reference-only
    d = _decomp("goldbach", ["lemma_3", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"], target_statement=GOLDBACH)
    assert is_reference_only(d) is False


def test_reference_only_genuine_subgoal_not_flagged():
    # A real proposition should not be flagged
    d = _decomp("goldbach", ["∃ p : ℕ, Nat.Prime p ∧ p ∣ n"], target_statement=GOLDBACH)
    assert is_reference_only(d) is False


def test_reference_only_degenerate_not_flagged():
    # Degenerate outputs return False (target restatement, not reference)
    d = _decomp("goldbach", [GOLDBACH], target_statement=GOLDBACH)
    assert is_reference_only(d) is False


def test_reference_only_true_not_flagged():
    # 'True' is a tautology, not a bare identifier reference
    d = _decomp("goldbach", ["True"], target_statement=GOLDBACH)
    assert is_reference_only(d) is False


# --- validity gate (compute_consensus excludes tautology + reference-only) ------


def test_validity_gate_tautology_excluded_from_jaccard():
    # Twin-primes pattern: gemma4-e4b produces "True", qwen3.5 produces real subgoals.
    # The tautology must not participate in Jaccard — it would inflate hardness spuriously
    # because {True} shares no tokens with real propositions.
    tautology = _decomp("twin-primes", ["True"], target_statement=TWIN_PRIMES)
    real = _decomp(
        "twin-primes",
        ["∃ p, Nat.Prime p ∧ Nat.Prime (p + 2)", "p > N"],
        target_statement=TWIN_PRIMES,
    )
    r = compute_consensus("twin-primes", [tautology, real])
    assert r.n_degenerate == 0
    assert r.n_invalid == 1  # tautology excluded
    assert r.n_models == 2
    # Only one valid model after exclusion → consensus undefined, not 1.0 (trivially same)
    assert r.consensus_score is None
    assert r.hardness_score is None
    # Novel statements come from the valid model only
    assert "∃ p, Nat.Prime p ∧ Nat.Prime (p + 2)" in r.novel_statements
    assert "True" not in r.novel_statements


def test_validity_gate_reference_only_excluded_from_jaccard():
    # Goldbach pattern: gemma4-e4b produces ["lemma_3"], gemma4-e2b produces real subgoals.
    # Without the gate, Jaccard({"lemma_3"}, {∃ k, …, ∃ p, …}) = 0 → hardness=1.0 (spurious).
    # With the gate, reference-only is excluded; only 1 valid model remains → hardness=None.
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    structured = _decomp(
        "goldbach",
        ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"],
        target_statement=GOLDBACH,
    )
    r = compute_consensus("goldbach", [ref_only, structured])
    assert r.n_degenerate == 0
    assert r.n_invalid == 1  # reference-only excluded
    assert r.n_models == 2
    assert r.consensus_score is None  # only 1 valid model
    assert r.hardness_score is None
    assert "∃ k : ℤ, n = 2 * k" in r.novel_statements
    assert "lemma_3" not in r.novel_statements


def test_validity_gate_both_tautology_and_reference_excluded():
    # Mixed invalid outputs: one tautology, one reference-only, two structured.
    # n_invalid should count both; Jaccard should use only the structured pair.
    tautology = _decomp("goldbach", ["True"], target_statement=GOLDBACH)
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    s1 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"], target_statement=GOLDBACH)
    s2 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "n = p + q"], target_statement=GOLDBACH)
    r = compute_consensus("goldbach", [tautology, ref_only, s1, s2])
    assert r.n_degenerate == 0
    assert r.n_invalid == 2  # tautology + reference-only
    assert r.n_models == 4
    # Two valid structured models → Jaccard computed on {∃ k : ℤ, n = 2 * k, ∃ p, …} vs {∃ k : ℤ, n = 2 * k, n = p + q}
    # intersection = {∃ k : ℤ, n = 2 * k}, union = 3 → Jaccard = 1/3
    assert r.consensus_score == pytest.approx(1 / 3)
    assert r.hardness_score == pytest.approx(2 / 3)


def test_validity_gate_all_invalid_returns_none():
    # All outputs are tautology or reference-only → no valid models → hardness undefined.
    tautology = _decomp("goldbach", ["True"], target_statement=GOLDBACH)
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    r = compute_consensus("goldbach", [tautology, ref_only])
    assert r.n_degenerate == 0
    assert r.n_invalid == 2
    assert r.consensus_score is None
    assert r.hardness_score is None
    assert r.novel_statements == frozenset()


def test_validity_gate_goldbach_pattern():
    # Full Goldbach case from beat 909/910: degenerate (qwen3.5) + reference-only (gemma4-e4b)
    # + structured-misdirected (gemma4-e2b). Spurious hardness was 1.0; after gate: None.
    degenerate = _decomp("goldbach", [GOLDBACH], target_statement=GOLDBACH)
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    misdirected = _decomp(
        "goldbach",
        ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"],
        target_statement=GOLDBACH,
    )
    r = compute_consensus("goldbach", [degenerate, ref_only, misdirected])
    assert r.n_degenerate == 1
    assert r.n_invalid == 1  # ref_only
    assert r.n_models == 3
    # Only misdirected passes the gate — 1 valid model → hardness undefined
    assert r.consensus_score is None
    assert r.hardness_score is None


def test_validity_gate_n_invalid_zero_for_normal_structured_outputs():
    # Standard case: two structured outputs with no tautologies or reference-only.
    # n_invalid must be 0.
    s1 = _decomp("twin-primes", ["∃ p, Nat.Prime p ∧ Nat.Prime (p + 2)", "p > N"], target_statement=TWIN_PRIMES)
    s2 = _decomp("twin-primes", ["Nat.Prime p", "Nat.Prime (p + 2)"], target_statement=TWIN_PRIMES)
    r = compute_consensus("twin-primes", [s1, s2])
    assert r.n_degenerate == 0
    assert r.n_invalid == 0
    assert r.consensus_score is not None  # two valid models → Jaccard computed
    assert r.hardness_score is not None


# --- diversity gate (n_distinct_models) -------------------------------------


def test_no_model_ids_n_distinct_is_zero():
    # When model_ids is omitted, n_distinct_models is 0 — no diversity tracking.
    s1 = _decomp("conj-1", ["A → B", "B → C"])
    s2 = _decomp("conj-1", ["A → B", "C → D"])
    r = compute_consensus("conj-1", [s1, s2])
    assert r.n_distinct_models == 0
    assert r.consensus_score is not None  # diversity gate inactive without IDs


def test_two_distinct_models_computes_jaccard():
    # Two valid decompositions from two different model IDs → Jaccard computed.
    s1 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"], target_statement=GOLDBACH)
    s2 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "n = p + q"], target_statement=GOLDBACH)
    r = compute_consensus("goldbach", [s1, s2], model_ids=["ren3/gemma4-e2b", "ren3/qwen3.5-9b-mlx"])
    assert r.n_distinct_models == 2
    assert r.consensus_score is not None
    assert r.hardness_score is not None


def test_diversity_gate_same_model_three_runs_returns_none():
    # Goldbach beat 910 pattern: validity gate filters gemma4-e4b (reference-only),
    # leaving gemma4-e2b × 3 identical runs. Jaccard is trivially 1.0 — not cross-model
    # signal. Diversity gate must suppress to None.
    s = _decomp(
        "goldbach",
        ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"],
        target_statement=GOLDBACH,
    )
    model_ids = ["ren3/gemma4-e2b", "ren3/gemma4-e2b", "ren3/gemma4-e2b"]
    r = compute_consensus("goldbach", [s, s, s], model_ids=model_ids)
    assert r.n_distinct_models == 1  # all from the same model
    assert r.consensus_score is None
    assert r.hardness_score is None
    # Novel statements still collected — the decomposition is real even if undiversified
    assert len(r.novel_statements) > 0


def test_diversity_gate_invalid_and_same_model():
    # Mixed: one reference-only (excluded by validity gate) + two runs of same model.
    # After validity gate: 2 valid, but same model → diversity gate fires.
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    s = _decomp(
        "goldbach",
        ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"],
        target_statement=GOLDBACH,
    )
    model_ids = ["ren3/gemma4-e4b", "ren3/gemma4-e2b", "ren3/gemma4-e2b"]
    r = compute_consensus("goldbach", [ref_only, s, s], model_ids=model_ids)
    assert r.n_invalid == 1  # ref_only excluded
    assert r.n_distinct_models == 1  # only gemma4-e2b valid
    assert r.consensus_score is None
    assert r.hardness_score is None


def test_diversity_gate_two_valid_different_models_one_invalid():
    # Two different valid models + one invalid → diversity gate passes.
    ref_only = _decomp("goldbach", ["lemma_3"], target_statement=GOLDBACH)
    s1 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "∃ p : ℕ, Nat.Prime p ∧ p ∣ n"], target_statement=GOLDBACH)
    s2 = _decomp("goldbach", ["∃ k : ℤ, n = 2 * k", "n = p + q"], target_statement=GOLDBACH)
    model_ids = ["ren3/gemma4-e4b", "ren3/gemma4-e2b", "ren3/qwen3.5-9b-mlx"]
    r = compute_consensus("goldbach", [ref_only, s1, s2], model_ids=model_ids)
    assert r.n_invalid == 1
    assert r.n_distinct_models == 2  # e2b and qwen3.5 both valid
    assert r.consensus_score is not None
    assert r.hardness_score is not None


def test_diversity_gate_length_mismatch_raises():
    s = _decomp("conj-1", ["A → B"])
    with pytest.raises(ValueError, match="model_ids length"):
        compute_consensus("conj-1", [s], model_ids=["m1", "m2"])


# --- _extract_top_level_conjuncts -------------------------------------------

CONSECUTIVE = "∀ n : ℕ, n ≤ n + 1 ∧ 2 ∣ n * (n + 1)"
EVEN_OR_ODD = "∀ n : ℕ, Even n ∨ Odd n"
GOLDBACH_TARGET = "∀ n : ℕ, 2 < n → Even n → ∃ p q : ℕ, Nat.Prime p ∧ Nat.Prime q ∧ p + q = n"
ADD_IDS = "∀ n : ℕ, n + 0 = n ∧ 0 + n = n"


def test_extract_conjuncts_conjunction():
    result = _extract_top_level_conjuncts(CONSECUTIVE)
    assert result == frozenset({"n ≤ n + 1", "2 ∣ n * (n + 1)"})


def test_extract_conjuncts_disjunction_returns_none():
    assert _extract_top_level_conjuncts(EVEN_OR_ODD) is None


def test_extract_conjuncts_implication_returns_none():
    # Goldbach has top-level →; the ∧ inside the ∃ should not be extracted.
    assert _extract_top_level_conjuncts(GOLDBACH_TARGET) is None


def test_extract_conjuncts_simple_conjunction():
    result = _extract_top_level_conjuncts(ADD_IDS)
    assert result == frozenset({"n + 0 = n", "0 + n = n"})


# --- canonical match in compute_consensus -----------------------------------


def test_canonical_match_conjunction_target():
    target = CONSECUTIVE
    # phi4 and gemma4-e4b both hit canonical: {n ≤ n + 1, 2 ∣ n * (n + 1)}
    d_canonical_a = _decomp("consecutive", ["∀ n : ℕ, n ≤ n + 1", "∀ n : ℕ, 2 ∣ n * (n + 1)"], target_statement=target)
    d_canonical_b = _decomp("consecutive", ["n ≤ n + 1", "2 ∣ n * (n + 1)"], target_statement=target)
    # gemma4-e2b confused conjunction with implication
    d_confused = _decomp("consecutive", ["∀ n : ℕ, n ≤ n + 1 → 2 ∣ n * (n + 1)", "∀ n : ℕ, n ≤ n + 1"], target_statement=target)
    r = compute_consensus("consecutive", [d_canonical_a, d_canonical_b, d_confused],
                          model_ids=["m1", "m2", "m3"])
    assert r.canonical_conjuncts == frozenset({"n ≤ n + 1", "2 ∣ n * (n + 1)"})
    assert r.n_canonical_match == 2  # only the two canonical decompositions match


def test_canonical_match_disjunction_target_is_none():
    target = EVEN_OR_ODD
    d1 = _decomp("eoo", ["∀ n : ℕ, Even n → Even n ∨ Odd n", "∀ n : ℕ, Odd n → Even n ∨ Odd n"], target_statement=target)
    d2 = _decomp("eoo", ["Even 0 ∨ Odd 0", "∀ k : ℕ, (Even k ∨ Odd k) → (Even (k+1) ∨ Odd (k+1))"], target_statement=target)
    r = compute_consensus("eoo", [d1, d2], model_ids=["m1", "m2"])
    assert r.canonical_conjuncts is None
    assert r.n_canonical_match is None


def test_canonical_match_no_valid_decompositions():
    target = CONSECUTIVE
    # All degenerate → no valid decompositions, n_canonical_match=0
    d_degen = _decomp("consecutive", [target], target_statement=target)
    r = compute_consensus("consecutive", [d_degen])
    assert r.canonical_conjuncts == frozenset({"n ≤ n + 1", "2 ∣ n * (n + 1)"})
    assert r.n_canonical_match == 0


# --- n_key_term_absent ------------------------------------------------------

GOLDBACH_TARGET = "∀ n : ℕ, 2 < n → Even n → ∃ p q : ℕ, Nat.Prime p ∧ Nat.Prime q ∧ p + q = n"
_GOLDBACH_CORRECT = ["Nat.Prime p ∧ Nat.Prime q", "p + q = n"]
_GOLDBACH_WRONG = ["Odd p ∧ Odd q", "p + q = n"]


def test_key_term_absent_no_required_predicates_returns_none():
    d = _decomp("g", _GOLDBACH_CORRECT, target_statement=GOLDBACH_TARGET)
    r = compute_consensus("g", [d, d], model_ids=["m1", "m2"])
    assert r.n_key_term_absent is None


def test_key_term_absent_all_present():
    d = _decomp("g", _GOLDBACH_CORRECT, target_statement=GOLDBACH_TARGET)
    r = compute_consensus("g", [d, d], model_ids=["m1", "m2"], required_predicates=["Nat.Prime"])
    assert r.n_key_term_absent == 0


def test_key_term_absent_wrong_predicate():
    d_wrong = _decomp("g", _GOLDBACH_WRONG, target_statement=GOLDBACH_TARGET)
    d_right = _decomp("g", _GOLDBACH_CORRECT, target_statement=GOLDBACH_TARGET)
    r = compute_consensus("g", [d_wrong, d_right], model_ids=["m1", "m2"],
                          required_predicates=["Nat.Prime"])
    assert r.n_key_term_absent == 1


def test_key_term_absent_all_wrong():
    d = _decomp("g", _GOLDBACH_WRONG, target_statement=GOLDBACH_TARGET)
    r = compute_consensus("g", [d, d], model_ids=["m1", "m2"], required_predicates=["Nat.Prime"])
    assert r.n_key_term_absent == 2


def test_key_term_absent_multiple_required_all_present():
    # Even-or-odd: both predicates present in one decomposition.
    d = _decomp("eoo", ["Even n", "Odd n"], target_statement="∀ n : ℕ, Even n ∨ Odd n")
    r = compute_consensus("eoo", [d, d], model_ids=["m1", "m2"],
                          required_predicates=["Even", "Odd"])
    assert r.n_key_term_absent == 0


def test_key_term_absent_multiple_required_one_missing():
    # Decomp mentions Even but not Odd — Odd predicate absent.
    # Use realistic multi-subgoal decomposition so it isn't caught by is_degenerate.
    d = _decomp("eoo", ["∃ k : ℕ, n = 2 * k", "Even n → Even n"],
                target_statement="∀ n : ℕ, Even n ∨ Odd n")
    r = compute_consensus("eoo", [d, d], model_ids=["m1", "m2"],
                          required_predicates=["Even", "Odd"])
    assert r.n_key_term_absent == 2


def test_key_term_absent_degenerate_excluded():
    # Degenerate decomp is not counted in n_key_term_absent.
    target = GOLDBACH_TARGET
    d_degen = _decomp("g", [target], target_statement=target)
    d_right = _decomp("g", _GOLDBACH_CORRECT, target_statement=target)
    r = compute_consensus("g", [d_degen, d_right], model_ids=["m1", "m2"],
                          required_predicates=["Nat.Prime"])
    # Only d_right is valid; it contains Nat.Prime → n_key_term_absent=0
    assert r.n_key_term_absent == 0


def test_key_term_absent_no_valid_decompositions_returns_zero():
    # All degenerate → real=[] → n_key_term_absent=0 (sum over empty set).
    target = GOLDBACH_TARGET
    d_degen = _decomp("g", [target], target_statement=target)
    r = compute_consensus("g", [d_degen], required_predicates=["Nat.Prime"])
    assert r.n_key_term_absent == 0
