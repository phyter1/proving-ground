"""Render a :class:`~proving_ground.results.Leaderboard` for humans.

Two outputs, both stdlib-only (f-strings, no jinja, no external deps):

* :func:`render_markdown` — one table per tier, for READMEs / PRs / chat.
* :func:`render_html` — a self-contained dark static page, the public leaderboard.

Both report **per tier** (docs/SCORING.md: a blended cross-tier number is dishonest) and
both call out nonzero ``open``-tier scores prominently — that is the headline fact the
benchmark exists to surface: a nonzero score on the ``open`` tier is a genuine
contribution to mathematics.
"""

from __future__ import annotations

import html
from pathlib import Path

from proving_ground.models import Tier
from proving_ground.results import Leaderboard

_TIER_LABEL: dict[Tier, str] = {
    Tier.SOLVED_RECENT: "solved_recent",
    Tier.WEAKLY_OPEN: "weakly_open",
    Tier.OPEN: "open",
}

_TIER_BLURB: dict[Tier, str] = {
    Tier.SOLVED_RECENT: (
        "Calibration / contamination canary. A model that fails here is broken, not "
        "challenged."
    ),
    Tier.WEAKLY_OPEN: (
        "Open to current provers but plausibly tractable. Moving the needle here is "
        "doing something real."
    ),
    Tier.OPEN: (
        "Genuinely open conjectures. No partial scalar is reported here — partial progress "
        "on an unsolved problem is not a real, ungameable quantity. We report solved "
        "(binary) and verified reductions that surface new open lemmas. Solving one is a "
        "contribution to mathematics."
    ),
}

_METRIC_LINE = (
    "Metric: kernel-verified partial credit = discharged subgoal weight / total weight "
    "(0 = none, 1.0 = a complete kernel-checked proof). Reported per tier — never blended. "
    "The open tier reports solved/reductions only, not a partial scalar (see the open-tier "
    "note for why)."
)


def _fmt(value: float) -> str:
    """Format a score in [0, 1] to three decimals."""
    return f"{value:.3f}"


# --- markdown --------------------------------------------------------------


def render_markdown(leaderboard: Leaderboard) -> str:
    """Render the leaderboard as markdown — one table per tier."""
    lines: list[str] = ["# proving-ground leaderboard", "", _METRIC_LINE, ""]

    artifacts = leaderboard.open_reduction_artifacts()
    if artifacts:
        lines.append("## 🏆 Open-tier results")
        lines.append("")
        lines.append(
            "**Genuinely open conjectures.** No partial scalar — solving one is binary and "
            "would be historic. What's reported is verified reductions and the new, smaller "
            "open lemmas they surface (which re-enter the corpus). ⭐ marks an actual solve:"
        )
        lines.append("")
        for s in artifacts:
            st = s.per_tier[Tier.OPEN]
            mark = "⭐ " if st.solved > 0 else ""
            solved_txt = f"{st.solved} solved, " if st.solved else ""
            lines.append(
                f"- {mark}**{s.model}** — {solved_txt}{st.verified_reductions} verified "
                f"reduction(s), {st.open_lemmas_surfaced} new open lemma(s) surfaced"
            )
        lines.append("")

    tiers = leaderboard.tiers()
    if not tiers:
        lines.append("_No results yet._")
        return "\n".join(lines) + "\n"

    for tier in tiers:
        lines.append(f"## Tier: `{_TIER_LABEL[tier]}`")
        lines.append("")
        lines.append(f"_{_TIER_BLURB[tier]}_")
        lines.append("")
        if tier is Tier.OPEN:
            lines.append(
                "| Rank | Model | Attempted | Solved | Verified reductions | "
                "Open lemmas surfaced |"
            )
            lines.append("|---:|---|---:|---:|---:|---:|")
            for rank, s in enumerate(leaderboard.rank_open(), start=1):
                st = s.per_tier[tier]
                model = f"⭐ {s.model}" if st.solved > 0 else s.model
                lines.append(
                    f"| {rank} | {model} | {st.attempted} | {st.solved} | "
                    f"{st.verified_reductions} | {st.open_lemmas_surfaced} |"
                )
        else:
            lines.append(
                "| Rank | Model | Attempted | Solved | Partial | Mean | Best |"
            )
            lines.append("|---:|---|---:|---:|---:|---:|---:|")
            for rank, s in enumerate(leaderboard.rank(tier), start=1):
                st = s.per_tier[tier]
                lines.append(
                    f"| {rank} | {s.model} | {st.attempted} | {st.solved} | {st.partial} | "
                    f"{_fmt(st.mean_score)} | {_fmt(st.best_score)} |"
                )
        lines.append("")

    return "\n".join(lines) + "\n"


# --- HTML ------------------------------------------------------------------

_CSS = """\
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1rem; background: #0d1117; color: #c9d1d9;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 1.8rem; margin: 0 0 .25rem; color: #f0f6fc; }
h2 { font-size: 1.2rem; margin: 2rem 0 .25rem; color: #f0f6fc; }
.metric { color: #8b949e; font-size: .9rem; margin: 0 0 1.5rem; }
.blurb { color: #8b949e; font-size: .85rem; margin: 0 0 .75rem; }
.headline {
  border: 1px solid #2ea043; background: #0f2417; border-radius: 8px;
  padding: 1rem 1.25rem; margin: 0 0 2rem;
}
.headline h2 { margin-top: 0; color: #3fb950; }
.headline ul { margin: .5rem 0 0; padding-left: 1.25rem; }
.headline code { color: #3fb950; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; margin-bottom: .5rem; }
th, td { padding: .5rem .6rem; text-align: right; border-bottom: 1px solid #21262d; }
th:nth-child(2), td:nth-child(2) { text-align: left; }
th:first-child, td:first-child { text-align: right; width: 3rem; }
thead th { color: #8b949e; font-weight: 600; border-bottom: 1px solid #30363d; }
tbody tr:hover { background: #161b22; }
.contrib td { color: #3fb950; font-weight: 600; }
.empty { color: #8b949e; font-style: italic; }
code { background: #161b22; padding: .1rem .35rem; border-radius: 4px; font-size: .85em; }
footer { margin-top: 2.5rem; color: #6e7681; font-size: .8rem; }
"""

_CLOSED_HEADERS = ("Rank", "Model", "Attempted", "Solved", "Partial", "Mean", "Best")
_OPEN_HEADERS = (
    "Rank", "Model", "Attempted", "Solved", "Verified reductions", "Open lemmas surfaced",
)


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _tds(cells: list[str], *, cls: str = "") -> str:
    return f"      <tr{cls}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _html_tier_section(leaderboard: Leaderboard, tier: Tier) -> str:
    rows: list[str] = []
    if tier is Tier.OPEN:
        headers = _OPEN_HEADERS
        for rank, s in enumerate(leaderboard.rank_open(), start=1):
            st = s.per_tier[tier]
            solved = st.solved > 0
            cls = ' class="contrib"' if solved else ""
            star = "⭐ " if solved else ""
            rows.append(_tds([
                str(rank), f"{star}{_esc(s.model)}", str(st.attempted), str(st.solved),
                str(st.verified_reductions), str(st.open_lemmas_surfaced),
            ], cls=cls))
    else:
        headers = _CLOSED_HEADERS
        for rank, s in enumerate(leaderboard.rank(tier), start=1):
            st = s.per_tier[tier]
            rows.append(_tds([
                str(rank), _esc(s.model), str(st.attempted), str(st.solved),
                str(st.partial), _fmt(st.mean_score), _fmt(st.best_score),
            ]))
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    rows_html = "\n".join(rows)
    return (
        f"    <section>\n"
        f"      <h2>Tier: <code>{_esc(_TIER_LABEL[tier])}</code></h2>\n"
        f'      <p class="blurb">{_esc(_TIER_BLURB[tier])}</p>\n'
        f"      <table>\n"
        f"        <thead><tr>{head}</tr></thead>\n"
        f"        <tbody>\n{rows_html}\n        </tbody>\n"
        f"      </table>\n"
        f"    </section>"
    )


def _html_headline(leaderboard: Leaderboard) -> str:
    artifacts = leaderboard.open_reduction_artifacts()
    if not artifacts:
        return ""
    items: list[str] = []
    for s in artifacts:
        st = s.per_tier[Tier.OPEN]
        mark = "⭐ " if st.solved > 0 else ""
        solved_txt = f"{st.solved} solved, " if st.solved else ""
        items.append(
            f"        <li>{mark}<strong>{_esc(s.model)}</strong> — {solved_txt}"
            f"{st.verified_reductions} verified reduction(s), "
            f"{st.open_lemmas_surfaced} new open lemma(s) surfaced</li>"
        )
    items_html = "\n".join(items)
    return (
        '    <section class="headline">\n'
        "      <h2>🏆 Open-tier results</h2>\n"
        "      <p>Genuinely open conjectures — no partial scalar (partial progress on an "
        "unsolved problem is not a real, ungameable quantity). Reported: verified reductions "
        "and the new open lemmas they surface (re-entering the corpus). ⭐ marks an actual "
        "solve.</p>\n"
        f"      <ul>\n{items_html}\n      </ul>\n"
        "    </section>"
    )


def render_html(leaderboard: Leaderboard) -> str:
    """Render a self-contained dark static HTML leaderboard page."""
    headline = _html_headline(leaderboard)
    tiers = leaderboard.tiers()
    if tiers:
        sections = "\n".join(_html_tier_section(leaderboard, t) for t in tiers)
    else:
        sections = '    <p class="empty">No results yet.</p>'

    body_parts = [p for p in (headline, sections) if p]
    body = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>proving-ground leaderboard</title>
  <style>
{_CSS}  </style>
</head>
<body>
  <main>
    <h1>proving-ground leaderboard</h1>
    <p class="metric">{_esc(_METRIC_LINE)}</p>
{body}
    <footer>
      A benchmark for LLMs on provably unsolved problems. Kernel-verified partial credit,
      reported per tier.
    </footer>
  </main>
</body>
</html>
"""


# --- site writer -----------------------------------------------------------


def write_site(
    leaderboard: Leaderboard,
    out_dir: str | Path,
    *,
    write_markdown: bool = True,
) -> None:
    """Write ``index.html`` (and optionally ``leaderboard.md``) into ``out_dir``.

    Creates ``out_dir`` if it does not exist.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_html(leaderboard), encoding="utf-8")
    if write_markdown:
        (out / "leaderboard.md").write_text(
            render_markdown(leaderboard), encoding="utf-8"
        )
