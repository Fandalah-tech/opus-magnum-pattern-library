from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_corpus import summarize_solution
from packages.opus_solver.solver import validate_generated_solution


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-sum465.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sum465_seed_has_expected_reference_topology() -> None:
    solution = _load(SOLUTION)
    entry = summarize_solution(solution, SOLUTION.name)

    assert entry.solution_name == "SUM465"
    assert entry.family == "sum-arm6-track"
    assert entry.active_arm_count == 3
    assert entry.instruction_count == 77
    assert solution["metrics"] == {
        "cycles": 214,
        "cost": 195,
        "area": 56,
        "instructions": 77,
    }


def test_sum465_seed_reaches_one_product_in_local_engine() -> None:
    puzzle = _load(PUZZLE)
    solution = _load(SOLUTION)

    validation = validate_generated_solution(puzzle, solution, target=1)

    assert validation["terminatedWithError"] is False
    assert validation["complete"] is True
    assert validation["deliveredProducts"].get("part-13", 0) >= 1
