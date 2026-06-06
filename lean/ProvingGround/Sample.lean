/-
A worked example of the submission shape the checker expects.

The benchmark gives a model an open `target` (here a deliberately trivial stand-in so the
file builds without mathlib). A submission is a *decomposition*: named lemmas, a proof
that the target follows from them (the root implication), and proofs of as many lemmas as
the model can close. Lemmas it cannot close are left as `sorry` — these are the open
sub-problems that re-enter the corpus.

The checker verifies each node independently and reports which are discharged; the metric
turns that into partial credit. "It compiles" is NOT "it's proven": `sorry` only warns, so
the checker also audits `#print axioms` for `sorryAx` and rejects it.
-/

namespace ProvingGround.Sample

/-- A discharged subgoal: fully proven, no `sorry`. -/
theorem lemma_one (n : Nat) : n + 0 = n := by
  simp

/-- An open subgoal: left as `sorry`. In a real problem this is a genuine open statement
that has been kernel-verified to (jointly) imply the target. It re-enters the corpus. -/
theorem lemma_two (n : Nat) : 0 + n = n := by
  sorry

/-- The target, reduced to the two lemmas above (the root implication). Here the reduction
is trivial; in a real problem this implication is the mathematically substantive step. -/
theorem target (n : Nat) : n + 0 = n ∧ 0 + n = n :=
  ⟨lemma_one n, lemma_two n⟩

-- The checker runs the equivalent of these and parses the output:
#print axioms lemma_one  -- expect: only standard axioms  -> discharged
#print axioms lemma_two  -- expect: depends on `sorryAx`   -> NOT discharged (open)

end ProvingGround.Sample
