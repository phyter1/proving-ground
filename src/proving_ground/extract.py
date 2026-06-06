"""Prompt construction and response extraction for the model runner.

This module is the bridge between a :class:`~proving_ground.models.Problem` and a raw
:class:`~proving_ground.checker.ProofArtifact`. It does *no* verification — it builds the
chat prompt that asks a model to produce a Lean decomposition, then parses the model's
free-text response into the structured artifact the checker consumes.

The split matters: extraction is a pure text transform, fully testable with no network and
no Lean toolchain. Whether the extracted Lean actually proves anything is the checker's
verdict, not ours.
"""

from __future__ import annotations

import json
import re

from proving_ground.checker import ProofArtifact
from proving_ground.models import Problem

# A fenced code block: ```lang\n...\n```. Language tag optional. Non-greedy body so
# multiple blocks in one response are matched independently.
_FENCE_RE = re.compile(
    r"```[ \t]*(?P<lang>[A-Za-z0-9_+-]*)[ \t]*\r?\n(?P<body>.*?)\r?\n?```",
    re.DOTALL,
)

# Lean declaration names: `theorem foo`, `lemma bar`, also `def`/`abbrev` used as subgoals.
_DECL_RE = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+|noncomputable\s+)*"
    r"(?:theorem|lemma|def|abbrev)\s+(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)",
    re.MULTILINE,
)


class ExtractionError(ValueError):
    """Raised when a model response cannot be parsed into a ProofArtifact.

    Carries the offending response (truncated) so callers can log what came back instead
    of guessing why parsing failed.
    """

    def __init__(self, message: str, *, response_text: str | None = None) -> None:
        if response_text is not None:
            snippet = response_text[:500]
            if len(response_text) > 500:
                snippet += "…"
            message = f"{message}\n--- response (truncated) ---\n{snippet}"
        super().__init__(message)


def build_prompt(problem: Problem) -> list[dict[str, str]]:
    """Build the chat messages asking a model to produce a Lean decomposition.

    The model is instructed to reuse the problem's preamble, restate the target verbatim,
    decompose it into named lemmas with a proof the target follows from them, prove what it
    can and leave the rest as ``sorry``, and emit both a fenced ``lean`` block and a fenced
    ``json`` manifest of subgoal ids. The anti-cheat gates from docs/SCORING.md are spelled
    out explicitly so the model knows what scores zero.
    """
    system = (
        "You are a Lean 4 / Mathlib expert collaborating on open mathematical problems. "
        "You are scored not on solving the problem outright but on how much *verifiable* "
        "progress you make. Progress means a verified reduction: a kernel-checked proof "
        "that the target follows from named lemmas, plus complete proofs of as many of "
        "those lemmas as you can close. Everything you emit is checked by the Lean kernel "
        "and an anti-cheat auditor. Claims that do not compile, or that lean on forbidden "
        "tactics, earn nothing. Be rigorous and honest about what you have actually proven."
    )

    user = f"""\
# Target problem

- id: {problem.id}
- title: {problem.title or "(untitled)"}
- tier: {problem.tier.value}
- source: {problem.source}

## Preamble (use exactly this; assume it is in scope)

```lean
{problem.preamble}
```

## Target statement (state it EXACTLY as given — do not alter it)

```lean
{problem.statement}
```

# Your task

Produce a Lean 4 *decomposition* of the target:

1. Begin with the preamble above, unchanged.
2. Restate the target as the final `theorem`, byte-for-byte identical to the statement \
above. Do not weaken it, generalize it, rename its binders, or change its type in any way.
3. Introduce a set of named **lemmas** (subgoals) that, taken together, imply the target. \
Give each a stable, descriptive name.
4. Prove the **root implication**: the final target theorem must follow from your lemmas \
by an explicit, complete proof (no `sorry` in the target proof itself).
5. Prove as many of the lemmas as you genuinely can, with complete kernel-checkable Lean \
proofs. For every lemma you cannot close, leave its proof body as exactly `sorry` — an \
honest open subgoal. Partial progress is the goal; do not fake completeness.

# Hard rules (any violation scores ZERO for the whole submission)

- DO NOT change the target statement's type or value. It is checked byte-identical to the \
frozen spec.
- DO NOT use `sorry` to fake a completed lemma or to close the root implication. `sorry` \
is ONLY allowed as the honest body of a lemma you are explicitly leaving open.
- DO NOT use `native_decide` (it is a soundness hole and is rejected by the axiom auditor). \
Avoid any tactic that introduces axioms outside `propext`, `Classical.choice`, `Quot.sound`.
- DO NOT close a lemma that is logically just the target itself (the null reduction \
"C follows from C" earns nothing).

# Output format (required)

First, a single fenced `lean` block containing the COMPLETE Lean source — preamble, every \
lemma (proved or `sorry`), and the final target theorem with its proof:

```lean
<your full Lean source here>
```

Then, a single fenced `json` block listing the subgoal lemma ids you introduced, in \
dependency order (the lemmas, NOT the final target theorem):

```json
{{"subgoal_ids": ["lemma_name_1", "lemma_name_2"]}}
```

Output the `lean` block and the `json` block and nothing else of substance. Prose outside \
the blocks is ignored by the parser.
"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _find_blocks(response_text: str) -> list[tuple[str, str]]:
    """Return all fenced code blocks as (language, body) pairs, in document order."""
    return [
        (m.group("lang").lower(), m.group("body"))
        for m in _FENCE_RE.finditer(response_text)
    ]


def _extract_lean_source(blocks: list[tuple[str, str]], response_text: str) -> str:
    """Pull the Lean source: prefer a ```lean block, else the first non-json block."""
    lean_blocks = [body for lang, body in blocks if lang == "lean"]
    if lean_blocks:
        # Last lean block wins — models often show a sketch then a final version.
        return lean_blocks[-1].strip()

    # No language tag? Fall back to the first block that is not obviously the manifest.
    non_json = [body for lang, body in blocks if lang != "json"]
    if non_json:
        return non_json[0].strip()

    raise ExtractionError(
        "No Lean code block found in model response (expected a ```lean fenced block).",
        response_text=response_text,
    )


def _extract_subgoal_ids(blocks: list[tuple[str, str]], lean_source: str) -> tuple[str, ...]:
    """Pull subgoal ids from the ```json manifest; fall back to scanning declarations."""
    for lang, body in blocks:
        if lang != "json":
            continue
        try:
            manifest = json.loads(body)
        except json.JSONDecodeError:
            continue
        ids = manifest.get("subgoal_ids") if isinstance(manifest, dict) else None
        if isinstance(ids, list):
            cleaned = tuple(str(i) for i in ids if str(i).strip())
            if cleaned:
                return cleaned

    # Fallback: scan the Lean source for declaration names.
    return _scan_declaration_names(lean_source)


def _scan_declaration_names(lean_source: str) -> tuple[str, ...]:
    """Scan Lean source for theorem/lemma/def declaration names, de-duplicated in order."""
    seen: set[str] = set()
    names: list[str] = []
    for m in _DECL_RE.finditer(lean_source):
        name = m.group("name")
        if name not in seen:
            seen.add(name)
            names.append(name)
    return tuple(names)


def extract_artifact(problem: Problem, response_text: str) -> ProofArtifact:
    """Parse a model's raw response into a :class:`ProofArtifact`.

    Pulls the Lean source from a fenced ``lean`` block and the subgoal ids from a fenced
    ``json`` manifest (falling back to scanning declaration names when no manifest is
    present). ``target_id`` and ``target_statement`` are taken from the problem, never from
    the model — the frozen spec is the source of truth.

    Raises:
        ExtractionError: if no Lean code block can be found.
    """
    if not response_text or not response_text.strip():
        raise ExtractionError("Empty model response.", response_text=response_text)

    blocks = _find_blocks(response_text)
    if not blocks:
        raise ExtractionError(
            "No fenced code blocks found in model response.",
            response_text=response_text,
        )

    lean_source = _extract_lean_source(blocks, response_text)
    subgoal_ids = _extract_subgoal_ids(blocks, lean_source)

    return ProofArtifact(
        target_id=problem.id,
        target_statement=problem.statement,
        lean_source=lean_source,
        subgoal_ids=subgoal_ids,
    )


__all__ = ["ExtractionError", "build_prompt", "extract_artifact"]
