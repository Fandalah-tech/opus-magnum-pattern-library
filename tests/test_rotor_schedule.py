from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_schedule import build_rotor_schedule


FIXTURE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")


def test_rotor_schedule_has_complete_serial_operation_inventory() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schedule = build_rotor_schedule(puzzle)

    assert schedule.supported is True
    assert schedule.transformation_steps == 6
    assert schedule.bond_steps == 6
    assert len(schedule.source_tokens) == 13
    assert len(schedule.product_tokens) == 7
    assert [step.kind for step in schedule.steps].count("pull") == 5
    assert schedule.steps[-2].kind == "assemble-disjoint"
    assert schedule.steps[-1].kind == "deliver"


def test_rotor_schedule_uses_each_source_and_target_once() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schedule = build_rotor_schedule(puzzle)

    routing = [step for step in schedule.steps if step.kind in {"route", "transform"}]
    assert len(routing) == 13
    assert len({step.inputs[0] for step in routing}) == 13
    assert len({step.outputs[0] for step in routing}) == 13


def test_rotor_schedule_final_components_are_six_dimers_and_one_isolated_atom() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schedule = build_rotor_schedule(puzzle)

    assert sum(token.startswith("dimer:") for token in schedule.product_tokens) == 6
    assert sum(token.startswith("target:") for token in schedule.product_tokens) == 1
