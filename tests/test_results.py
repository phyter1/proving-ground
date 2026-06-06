"""Tests for results aggregation and JSON round-tripping.

Fixtures cover two models across all three tiers, with a mix of solved / partial / zero
scores, so the per-tier grouping and ranking are exercised end to end.
"""

from __future__ import annotations

from proving_ground.models import RunResult, Score, ScoreKind, Tier
from proving_ground.results import (
    Leaderboard,
    ModelStanding,
    aggregate,
    dump_results,
    load_results,
)


# --- fixtures --------------------------------------------------------------


def _score(value: float, *, open_ids: tuple[str, ...] = ()) -> Score:
    if value >= 1.0:
        kind = ScoreKind.SOLVED
    elif value > 0.0:
        kind = ScoreKind.REDUCTION
    else:
        kind = ScoreKind.NONE
    return Score(
        value=value,
        kind=kind,
        discharged_weight=value * 2.0,
        total_weight=2.0,
        remaining_open_ids=open_ids,
        rationale=f"test score {value}",
    )


def _result(model: str, pid: str, tier: Tier, value: float, **kw) -> RunResult:
    return RunResult(
        model=model,
        problem_id=pid,
        tier=tier,
        score=_score(value, **kw),
        timestamp="2026-06-06T00:00:00Z",
    )


def _fixtures() -> list[RunResult]:
    return [
        # model-a: strong on solved_recent, partial on weakly_open, nonzero on open
        _result("model-a", "sr-1", Tier.SOLVED_RECENT, 1.0),
        _result("model-a", "sr-2", Tier.SOLVED_RECENT, 1.0),
        _result("model-a", "wo-1", Tier.WEAKLY_OPEN, 0.5, open_ids=("L1",)),
        _result("model-a", "op-1", Tier.OPEN, 0.25, open_ids=("L2", "L3", "L4")),
        # model-b: weaker on solved_recent, zero everywhere open
        _result("model-b", "sr-1", Tier.SOLVED_RECENT, 1.0),
        _result("model-b", "sr-2", Tier.SOLVED_RECENT, 0.0),
        _result("model-b", "wo-1", Tier.WEAKLY_OPEN, 0.0, open_ids=("L1", "L5")),
        _result("model-b", "op-1", Tier.OPEN, 0.0, open_ids=("L2", "L3")),
    ]


# --- aggregation grouping --------------------------------------------------


def test_aggregate_groups_by_model_and_tier():
    lb = aggregate(_fixtures())
    assert isinstance(lb, Leaderboard)
    models = {s.model for s in lb.standings}
    assert models == {"model-a", "model-b"}
    a = next(s for s in lb.standings if s.model == "model-a")
    assert set(a.per_tier) == {Tier.SOLVED_RECENT, Tier.WEAKLY_OPEN, Tier.OPEN}


def test_per_tier_means_and_counts():
    lb = aggregate(_fixtures())
    a = next(s for s in lb.standings if s.model == "model-a")
    b = next(s for s in lb.standings if s.model == "model-b")

    sr_a = a.stats(Tier.SOLVED_RECENT)
    assert sr_a.attempted == 2
    assert sr_a.solved == 2
    assert sr_a.partial == 0
    assert sr_a.mean_score == 1.0
    assert sr_a.best_score == 1.0

    wo_a = a.stats(Tier.WEAKLY_OPEN)
    assert wo_a.attempted == 1
    assert wo_a.partial == 1
    assert wo_a.solved == 0
    assert wo_a.mean_score == 0.5
    assert wo_a.open_lemmas_surfaced == 1

    sr_b = b.stats(Tier.SOLVED_RECENT)
    assert sr_b.attempted == 2
    assert sr_b.solved == 1
    assert sr_b.mean_score == 0.5

    op_b = b.stats(Tier.OPEN)
    assert op_b.best_score == 0.0
    assert op_b.open_lemmas_surfaced == 2


def test_open_lemmas_surfaced_sums_across_attempts():
    lb = aggregate(_fixtures())
    a = next(s for s in lb.standings if s.model == "model-a")
    assert a.stats(Tier.OPEN).open_lemmas_surfaced == 3


def test_does_not_blend_across_tiers():
    # model-a's open mean must NOT be contaminated by its perfect solved_recent scores.
    lb = aggregate(_fixtures())
    a = next(s for s in lb.standings if s.model == "model-a")
    assert a.stats(Tier.OPEN).mean_score == 0.25


# --- ranking ---------------------------------------------------------------


def test_rank_orders_by_solved_then_mean():
    lb = aggregate(_fixtures())
    ranked = lb.rank(Tier.SOLVED_RECENT)
    # model-a: 2 solved; model-b: 1 solved -> model-a first.
    assert [s.model for s in ranked] == ["model-a", "model-b"]


def test_rank_excludes_models_without_tier():
    results = [
        _result("only-sr", "sr-1", Tier.SOLVED_RECENT, 1.0),
        _result("has-open", "op-1", Tier.OPEN, 0.5, open_ids=("L1",)),
    ]
    lb = aggregate(results)
    ranked_open = lb.rank(Tier.OPEN)
    assert [s.model for s in ranked_open] == ["has-open"]


def test_rank_tiebreak_by_mean_then_best():
    # Equal solved counts (0), distinguish by mean score.
    results = [
        _result("m-low", "wo-1", Tier.WEAKLY_OPEN, 0.2),
        _result("m-high", "wo-1", Tier.WEAKLY_OPEN, 0.8),
    ]
    lb = aggregate(results)
    ranked = lb.rank(Tier.WEAKLY_OPEN)
    assert [s.model for s in ranked] == ["m-high", "m-low"]


# --- open-tier headline ----------------------------------------------------


def test_open_contribution_flag():
    lb = aggregate(_fixtures())
    a = next(s for s in lb.standings if s.model == "model-a")
    b = next(s for s in lb.standings if s.model == "model-b")
    assert a.open_contribution() is True
    assert b.open_contribution() is False


def test_open_contributors_lists_only_nonzero_open():
    lb = aggregate(_fixtures())
    contributors = lb.open_contributors()
    assert [s.model for s in contributors] == ["model-a"]


# --- round trip ------------------------------------------------------------


def test_load_dump_round_trip(tmp_path):
    results = _fixtures()
    path = tmp_path / "results.json"
    dump_results(results, path)
    loaded = load_results(path)
    assert loaded == results


def test_round_trip_preserves_types(tmp_path):
    results = [_result("m", "op-1", Tier.OPEN, 0.25, open_ids=("L1", "L2"))]
    path = tmp_path / "r.json"
    dump_results(results, path)
    loaded = load_results(path)
    r = loaded[0]
    assert isinstance(r.tier, Tier)
    assert isinstance(r.score.kind, ScoreKind)
    assert r.score.remaining_open_ids == ("L1", "L2")
    assert r.artifact_ref is None


def test_load_rejects_non_array(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")
    try:
        load_results(path)
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-array JSON")


def test_modelstanding_is_frozen():
    s = ModelStanding(model="x")
    try:
        s.model = "y"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("ModelStanding should be frozen")
