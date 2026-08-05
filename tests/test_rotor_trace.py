from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_trace import trace_solution_milestones


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-sum465.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sum465_trace_is_complete_and_delivers_six_products() -> None:
    trace = trace_solution_milestones(_load(PUZZLE), _load(SOLUTION))

    assert trace.terminated_with_error is False
    assert dict(trace.delivered_products).get("part-13", 0) >= 6
    assert sum(item.kind == "product-delivered" for item in trace.milestones) >= 6


def test_sum465_trace_exposes_assembly_events_for_macro_learning() -> None:
    trace = trace_solution_milestones(_load(PUZZLE), _load(SOLUTION))
    kinds = {item.kind for item in trace.milestones}

    assert "product-delivered" in kinds
    assert kinds & {"bond-created", "floating-bond-created"}
    assert kinds & {"atom-calcified", "atom-duplicated"}
