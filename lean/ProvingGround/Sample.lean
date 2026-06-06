/-
A worked example of the submission shape the checker expects — the *verified reduction*
protocol (deliberately trivial statements so the file builds without heavy mathlib).

The benchmark gives a model an open `target`. A submission is:

  * named **lemma theorems** (the subgoals), each proved or left `:= by sorry`;
  * one **reduction theorem** named `reduction` that takes the lemma *statements* as
    hypotheses and concludes the target exactly.

Taking the lemmas as hypotheses is the crux: `#print axioms` is transitive, so if the
target were proven directly from a sorried lemma it would report `sorryAx` and no partial
credit would be possible. As hypotheses, the reduction is verified independently of whether
the lemmas are proven — so a partially-completed decomposition still earns its fraction.

The checker (proving_ground.checker.LeanInteractChecker) verifies, against a live kernel:
  1. `#print axioms <lemma>` is clean  -> that lemma is discharged;
  2. `#print axioms reduction` is clean -> the reduction has no sorry / native_decide;
  3. `example : <H1> → <H2> → <target> := @reduction` elaborates -> the reduction really
     concludes the frozen target (statement integrity / anti-tampering).
-/

namespace ProvingGround.Sample

/-- A discharged subgoal: fully proven, no `sorry`. -/
theorem sg_left (n : Nat) : n + 0 = n := by simp

/-- An open subgoal: left as `sorry`. It re-enters the corpus as a new open problem. -/
theorem sg_right (n : Nat) : 0 + n = n := by sorry

/-- The reduction: the target `(n + 0 = n) ∧ (0 + n = n)` follows from the two lemma
statements taken as hypotheses. This proof is complete (no `sorry`) and concludes exactly
the target, so the reduction is credited; the score is then the fraction of lemmas
discharged (here 1/2, since `sg_right` is open). -/
theorem reduction (n : Nat) :
    (n + 0 = n) → (0 + n = n) → ((n + 0 = n) ∧ (0 + n = n)) :=
  fun h1 h2 => ⟨h1, h2⟩

-- What the checker runs (illustrative):
#print axioms sg_left    -- [propext]  -> clean -> discharged
#print axioms sg_right   -- [sorryAx]  -> NOT clean -> open subgoal
#print axioms reduction  -- clean      -> reduction credited

end ProvingGround.Sample
