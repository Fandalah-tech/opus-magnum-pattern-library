from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_macros import extract_product_macros, learn_rotor_macros
from packages.opus_solver.rotor_trace import RotorTrace, TraceMilestone


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-sum465.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_synthetic_trace_is_segmented_into_startup_and_products() -> None:
    trace = RotorTrace(
        completed_cycles=30,
        terminated_with_error=False,
        milestones=(
            TraceMilestone(2, "bond-created", {"id": "setup"}),
            TraceMilestone(10, "product-delivered", {"output": "o"}),
            TraceMilestone(15, "bond-created", {"id": "a"}),
            TraceMilestone(20, "product-delivered", {"output": "o"}),
            TraceMilestone(25, "bond-created", {"id": "b"}),
            TraceMilestone(30, "product-delivered", {"output": "o"}),
        ),
        delivered_products=(("o", 3),),
    )

    program = extract_product_macros(trace)

    assert len(program.startup) == 1
    assert len(program.products) == 3
    assert program.steady_state_period == 10
    assert program.stable_from_product == 1
    assert program.products[1].events[-1].kind == "product-delivered"


def test_sum465_yields_six_delivery_macros() -> None:
    program = learn_rotor_macros(_load(PUZZLE), _load(SOLUTION))

    assert len(program.products) == 6
    assert all(product.events[-1].kind == "product-delivered" for product in program.products)
    assert all(product.duration > 0 for product in program.products)
    assert program.steady_state_period is not None
    assert program.event_signature
