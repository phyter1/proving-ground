"""CLI smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from proving_ground.cli import main


def test_score_example_problem(capsys):
    example = Path(__file__).parent.parent / "problems" / "example-reduction.json"
    rc = main(["score", str(example)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # base-case (w=1) discharged, inductive-step (w=3) open => 1/4.
    assert out["value"] == 0.25
    assert out["kind"] == "reduction"
    assert out["remaining_open_ids"] == ["inductive-step"]
