"""Tests for markdown and HTML leaderboard rendering."""

from __future__ import annotations

from proving_ground.leaderboard import (
    render_html,
    render_markdown,
    write_site,
)
from proving_ground.models import RunResult, Score, ScoreKind, Tier
from proving_ground.results import aggregate


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
        discharged_weight=value,
        total_weight=1.0,
        remaining_open_ids=open_ids,
        rationale="t",
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
        _result("model-a", "sr-1", Tier.SOLVED_RECENT, 1.0),
        _result("model-a", "wo-1", Tier.WEAKLY_OPEN, 0.5, open_ids=("L1",)),
        _result("model-a", "op-1", Tier.OPEN, 0.25, open_ids=("L2", "L3")),
        _result("model-b", "sr-1", Tier.SOLVED_RECENT, 0.0),
        _result("model-b", "op-1", Tier.OPEN, 0.0, open_ids=("L4",)),
    ]


def _board():
    return aggregate(_fixtures())


# --- markdown --------------------------------------------------------------


def test_markdown_has_each_tier_heading():
    md = render_markdown(_board())
    assert "solved_recent" in md
    assert "weakly_open" in md
    assert "open" in md


def test_markdown_has_each_model():
    md = render_markdown(_board())
    assert "model-a" in md
    assert "model-b" in md


def test_markdown_mentions_partial_credit_metric():
    md = render_markdown(_board())
    assert "partial credit" in md.lower()


def test_markdown_highlights_open_contribution():
    md = render_markdown(_board())
    # Headline section calls out the open-tier verified reductions; nonzero gets a star.
    assert "Open-tier verified reductions" in md
    assert "⭐" in md


def test_markdown_empty_board():
    md = render_markdown(aggregate([]))
    assert "No results yet" in md


# --- html ------------------------------------------------------------------


def test_html_is_valid_ish():
    h = render_html(_board())
    assert "<!DOCTYPE html>" in h
    assert "<html" in h
    assert "</html>" in h
    assert "<style>" in h
    # self-contained: no external resource references
    assert "http://" not in h
    assert "https://" not in h


def test_html_has_each_tier_and_model():
    h = render_html(_board())
    for tier in ("solved_recent", "weakly_open", "open"):
        assert tier in h
    assert "model-a" in h
    assert "model-b" in h


def test_html_highlights_open_contribution():
    h = render_html(_board())
    assert "Open-tier verified reductions" in h
    assert "contrib" in h  # the highlighted row / section class
    assert "⭐" in h


def test_html_escapes_model_names():
    results = [_result("<script>", "op-1", Tier.OPEN, 0.5, open_ids=("L1",))]
    h = render_html(aggregate(results))
    assert "<script>" not in h
    assert "&lt;script&gt;" in h


def test_html_empty_board():
    h = render_html(aggregate([]))
    assert "No results yet" in h
    assert "<html" in h


# --- site writer -----------------------------------------------------------


def test_write_site_creates_files(tmp_path):
    out = tmp_path / "site"
    write_site(_board(), out)
    assert (out / "index.html").exists()
    assert (out / "leaderboard.md").exists()
    assert "<!DOCTYPE html>" in (out / "index.html").read_text(encoding="utf-8")


def test_write_site_can_skip_markdown(tmp_path):
    out = tmp_path / "site2"
    write_site(_board(), out, write_markdown=False)
    assert (out / "index.html").exists()
    assert not (out / "leaderboard.md").exists()
