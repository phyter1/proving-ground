"""Corpus adapters and the self-renewing engine.

A benchmark needs a supply of :class:`~proving_ground.models.Problem`s. This module
normalizes three sources into that single shape:

1. ``parse_formal_conjecture`` — DeepMind's ``google-deepmind/formal-conjectures``: open
   conjectures formalized in Lean and marked with ``sorry`` (solved ones carry
   ``@[formal_proof ...]``).
2. ``parse_sorrydb`` — ``SorryDB``-style JSON: real ``sorry``s harvested from active Lean
   repositories.
3. ``renew_from_decomposition`` — THE SELF-RENEWING ENGINE: when a model produces a
   kernel-verified reduction, the leftover open lemmas
   (:attr:`Decomposition.remaining_open`) become new, smaller open problems fed back into
   the corpus.

Plus dedup and JSON (de)serialization helpers. Everything here is pure-Python stdlib —
no Lean toolchain, no third-party deps — matching the rest of the metric layer.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from proving_ground.models import Decomposition, Problem, Tier

# --- Lean-source parsing (formal-conjectures) ------------------------------

# Match a theorem/lemma declaration up to its proof body. We capture the name, the
# signature (binders + ``: TYPE``), and the body that follows ``:=``. This is deliberately
# pragmatic and regex-based — a full Lean parser is out of scope. We anchor on the
# declaration keyword and stop the type at the top-level ``:=`` that begins the proof.
_DECL_RE = re.compile(
    r"""
    ^[^\S\r\n]*                              # leading indentation
    (?:theorem|lemma)\s+                     # declaration keyword
    (?P<name>[A-Za-z_][\w.'!?]*)             # declaration name
    (?P<sig>.*?)                             # binders + ``: TYPE`` (non-greedy)
    \s*:=\s*                                 # the ``:=`` that starts the proof body
    (?P<body>.*?)                            # proof body
    (?=^\s*(?:theorem|lemma|@\[|/--|/-|namespace|section|end\b)|\Z)
    """,
    re.VERBOSE | re.DOTALL | re.MULTILINE,
)

# Within a signature, the statement type is everything after the first top-level ``:``.
# We track bracket/paren depth so a ``:`` inside binders like ``(n : Nat)`` is skipped.
_OPEN_BRACKETS = {"(": ")", "[": "]", "{": "}", "⟨": "⟩"}
_CLOSE_BRACKETS = set(_OPEN_BRACKETS.values())

_URL_RE = re.compile(r"https?://[^\s)\]}>'\"]+")
_IMPORT_RE = re.compile(r"^\s*import\s+\S+.*$", re.MULTILINE)
# ``sorry`` as a whole token, not as a substring of an identifier.
_SORRY_RE = re.compile(r"(?<![\w.])sorry(?![\w])")
_FORMAL_PROOF_RE = re.compile(r"@\[\s*formal_proof\b")


def _extract_statement(sig: str) -> str:
    """Pull the Lean type out of a declaration signature.

    ``sig`` is everything between the declaration name and the ``:=``. The statement is
    the text after the first *top-level* ``:`` (depth 0); ``:`` inside binders such as
    ``(n : Nat)`` are ignored via bracket-depth tracking.
    """
    depth = 0
    for i, ch in enumerate(sig):
        if ch in _OPEN_BRACKETS:
            depth += 1
        elif ch in _CLOSE_BRACKETS:
            depth -= 1
        elif ch == ":" and depth == 0:
            return sig[i + 1 :].strip()
    # No top-level type annotation found; fall back to the whole signature, trimmed.
    return sig.strip()


def _collect_urls(text: str) -> tuple[str, ...]:
    """Return URLs found in ``text`` (typically comments), de-duplicated, in order."""
    seen: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        if url not in seen:
            seen.append(url)
    return tuple(seen)


def _preamble_from(source_text: str) -> str:
    """Collect ``import`` lines; default to ``import Mathlib`` when none are present."""
    imports = [m.group(0).strip() for m in _IMPORT_RE.finditer(source_text)]
    if not imports:
        return "import Mathlib"
    return "\n".join(imports)


def parse_formal_conjecture(
    lean_source: str, *, source: str = "formal-conjectures"
) -> list[Problem]:
    """Extract theorem/conjecture statements from a Lean source snippet.

    For each ``theorem``/``lemma`` declaration we identify the declared statement (the
    type after the top-level ``:``), classify the tier, and build a :class:`Problem`:

    - A declaration whose proof body is/contains ``sorry`` → :attr:`Tier.OPEN`.
    - A declaration with a real proof (``@[formal_proof]`` attribute, or simply no
      ``sorry`` in the body) → :attr:`Tier.SOLVED_RECENT`.

    The title is the declaration name. ``references`` are URLs found anywhere in the
    snippet's comments. ``preamble`` is the import lines found, defaulting to
    ``import Mathlib``. One Problem is returned per declaration, in source order.

    This is intentionally regex-based and pragmatic — not a full Lean parser. It handles
    the common shapes in ``formal-conjectures`` (``:= by sorry``, ``:= sorry``, real
    proofs) and is covered by tests rather than by completeness guarantees.
    """
    preamble = _preamble_from(lean_source)
    urls = _collect_urls(lean_source)

    problems: list[Problem] = []
    for m in _DECL_RE.finditer(lean_source):
        name = m.group("name")
        statement = _extract_statement(m.group("sig"))
        if not statement:
            # Nothing usable as a frozen spec; skip rather than emit a hollow Problem.
            continue
        body = m.group("body")

        # Attribute block immediately preceding the declaration tells us if it's a
        # registered formal proof. We look at the source up to this match's start.
        prefix = lean_source[: m.start()]
        has_formal_proof_attr = bool(_FORMAL_PROOF_RE.search(prefix.rsplit("\n\n", 1)[-1]))
        body_has_sorry = bool(_SORRY_RE.search(body))

        if body_has_sorry and not has_formal_proof_attr:
            tier = Tier.OPEN
        else:
            tier = Tier.SOLVED_RECENT

        problems.append(
            Problem(
                id=f"{source}::{name}",
                statement=statement,
                tier=tier,
                source=source,
                title=name,
                references=urls,
                preamble=preamble,
            )
        )
    return problems


# --- SorryDB JSON records --------------------------------------------------

# SorryDB records vary; these are the field names we have seen used for the goal text and
# for a provided identifier. We probe them in order and fall back defensively.
_STATEMENT_KEYS = ("goal", "statement", "type", "sorry_type", "goalState")
_ID_KEYS = ("id", "uuid", "hash", "sorry_id", "_id")
_REPO_KEYS = ("repo", "repository", "repo_url", "url")
_FILE_KEYS = ("file", "path", "file_path", "location", "loc")


def _first_present(record: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = record.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _hashed_id(statement: str) -> str:
    """A stable id derived from the statement text (for records lacking their own id)."""
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()[:16]
    return f"sorrydb::{digest}"


def parse_sorrydb(records: list[dict]) -> list[Problem]:
    """Map SorryDB-style JSON records into :class:`Problem`s (tier :attr:`Tier.OPEN`).

    SorryDB harvests real ``sorry``s from active Lean repositories, so every record is an
    open problem by construction. Records are heterogeneous; we are defensive about
    missing fields:

    - The statement is taken from the first present of ``goal``/``statement``/``type``/...
      Records with no usable statement text are skipped.
    - The id is the first present of ``id``/``uuid``/``hash``/...; if none exists we derive
      a stable id by hashing the statement, so re-ingesting the same sorry is idempotent.
    - Repo and file location, when present, are recorded in ``metadata`` for provenance.
    """
    problems: list[Problem] = []
    for record in records:
        statement = _first_present(record, _STATEMENT_KEYS)
        if statement is None:
            # No goal text means nothing to verify against; skip.
            continue
        statement = statement.strip()

        problem_id = _first_present(record, _ID_KEYS)
        if problem_id is None:
            problem_id = _hashed_id(statement)
        else:
            problem_id = f"sorrydb::{problem_id}"

        metadata: dict[str, str] = {}
        repo = _first_present(record, _REPO_KEYS)
        if repo is not None:
            metadata["repo"] = repo
        file_loc = _first_present(record, _FILE_KEYS)
        if file_loc is not None:
            metadata["file"] = file_loc

        references = (repo,) if repo and repo.startswith(("http://", "https://")) else ()
        title = _first_present(record, ("name", "title", "decl")) or ""

        problems.append(
            Problem(
                id=problem_id,
                statement=statement,
                tier=Tier.OPEN,
                source="sorrydb",
                title=title,
                references=references,
                metadata=metadata,
            )
        )
    return problems


# --- The self-renewing engine ----------------------------------------------

def renew_from_decomposition(
    decomp: Decomposition,
    *,
    parent_problem_id: str,
    tier: Tier = Tier.WEAKLY_OPEN,
) -> list[Problem]:
    """Turn the leftover open subgoals of a verified reduction into new Problems.

    This is the self-renewing engine described in docs/SCORING.md. When a model proves a
    reduction ``(L₁ ∧ … ∧ Lₖ) → C`` and discharges some but not all of the ``Lᵢ``, the
    remaining-open lemmas are each kernel-verified to *jointly* imply a known open
    conjecture. They are therefore legitimate, smaller open problems and flow back into
    the corpus.

    Each new Problem gets:

    - ``id`` of the form ``f"{parent_problem_id}::{subgoal.id}"`` (composite, stable),
    - ``statement`` = the subgoal's statement,
    - ``source`` = ``"self-renewed"``,
    - ``metadata`` recording the parent problem id and the originating subgoal id,
    - ``tier`` defaulting to :attr:`Tier.WEAKLY_OPEN` (a sub-lemma of an open problem is
      plausibly more tractable than the parent).

    Grounding requirement: we return ``[]`` when ``decomp.root_implication_verified`` is
    False. Without a kernel-verified root implication the "reduction" is just relocating
    the ``sorry`` — there is no logical connection between the subgoals and the target, so
    the leftovers are *not* verified to imply anything and have no claim to being real
    sub-problems. Emitting them would manufacture ungrounded corpus entries, exactly the
    failure the root-implication hard gate exists to prevent.
    """
    if not decomp.root_implication_verified:
        return []

    problems: list[Problem] = []
    for subgoal in decomp.remaining_open:
        problems.append(
            Problem(
                id=f"{parent_problem_id}::{subgoal.id}",
                statement=subgoal.statement,
                tier=tier,
                source="self-renewed",
                title=subgoal.id,
                metadata={
                    "parent_problem_id": parent_problem_id,
                    "parent_target_id": decomp.target_id,
                    "subgoal_id": subgoal.id,
                },
            )
        )
    return problems


# --- Dedup -----------------------------------------------------------------

def _normalize_statement(statement: str) -> str:
    """Collapse all runs of whitespace to single spaces and strip ends."""
    return " ".join(statement.split())


def dedup(problems: list[Problem]) -> list[Problem]:
    """Drop duplicate problems by normalized statement, keeping the first occurrence.

    "Duplicate" means whitespace-normalized statement equality (runs of whitespace
    collapsed, ends stripped). This is an *approximate* identity: two problems with the
    same statement text are treated as the same problem even if their ids/sources differ,
    and conversely two logically-equivalent statements written differently (alpha-renamed
    binders, reordered hypotheses) are NOT detected as duplicates. Statement-identity
    dedup is intentionally cheap and conservative; true logical dedup would require the
    Lean kernel and is out of scope for this layer.
    """
    seen: set[str] = set()
    result: list[Problem] = []
    for problem in problems:
        key = _normalize_statement(problem.statement)
        if key in seen:
            continue
        seen.add(key)
        result.append(problem)
    return result


# --- JSON (de)serialization ------------------------------------------------

def _problem_to_dict(problem: Problem) -> dict:
    return {
        "id": problem.id,
        "statement": problem.statement,
        "tier": problem.tier.value,
        "source": problem.source,
        "title": problem.title,
        "references": list(problem.references),
        "preamble": problem.preamble,
        "proved_after": problem.proved_after,
        "metadata": dict(problem.metadata),
    }


def _problem_from_dict(data: dict) -> Problem:
    return Problem(
        id=data["id"],
        statement=data["statement"],
        tier=Tier(data["tier"]),
        source=data["source"],
        title=data.get("title", ""),
        references=tuple(data.get("references", ())),
        preamble=data.get("preamble", "import Mathlib"),
        proved_after=data.get("proved_after"),
        metadata=dict(data.get("metadata", {})),
    )


def save_corpus(problems: list[Problem], path: str | Path) -> None:
    """Serialize a list of Problems to JSON at ``path``.

    Tier enums are written as their string values, ``references`` tuples as lists, and
    ``metadata`` as a plain object — a shape that round-trips cleanly through
    :func:`load_corpus`.
    """
    payload = [_problem_to_dict(p) for p in problems]
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_corpus(path: str | Path) -> list[Problem]:
    """Load a list of Problems from a JSON file written by :func:`save_corpus`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_problem_from_dict(item) for item in raw]
