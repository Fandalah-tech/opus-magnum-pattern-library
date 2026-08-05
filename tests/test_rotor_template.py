from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_macros import learn_rotor_macros
from packages.opus_solver.rotor_template import build_steady_state_template


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-sum465.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sum465_produces_reusable_35_cycle_template() -> None:
    program = learn_rotor_macros(_load(PUZZLE), _load(SOLUTION))
    template = build_steady_state_template(program)

    assert template is not None
    assert template.period == 35
    assert template.source_product_indices == (1, 2, 3, 4, 5)
    assert template.exact_timing_match is True
    assert any(event.kind == "product-delivered" for event in template.events)
    assert sum(event.occurrences_per_product for event in template.events if event.kind == "bond-removed") == 1
    assert sum(event.occurrences_per_product for event in template.events if event.kind == "bond-created") == 7
