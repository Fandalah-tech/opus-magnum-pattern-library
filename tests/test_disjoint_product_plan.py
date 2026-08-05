from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.disjoint_plan import build_disjoint_product_plan


FIXTURE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")


def test_van_berlo_rotor_decomposes_into_six_dimers_and_one_isolated_atom() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    plan = build_disjoint_product_plan(puzzle)

    assert plan.supported is True
    assert sorted(len(component.atom_ids) for component in plan.components) == [1, 2, 2, 2, 2, 2, 2]
    assert plan.isolated_atoms == 1
    assert plan.required_bonds == 6


def test_van_berlo_rotor_element_demand_and_conversion_lower_bound() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    plan = build_disjoint_product_plan(puzzle)

    assert dict(plan.element_demand) == {
        "air": 2,
        "earth": 2,
        "fire": 2,
        "salt": 5,
        "water": 2,
    }
    assert dict(plan.reagent_element_supply[0][1]) == {"salt": 1, "water": 1}
    assert dict(plan.reagent_element_supply[1][1]) == {"salt": 3}
    assert plan.required_transmutations == 7


def test_each_bonded_component_is_a_product_dimer() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    plan = build_disjoint_product_plan(puzzle)
    dimers = [component for component in plan.components if len(component.atom_ids) == 2]

    assert len(dimers) == 6
    assert all(component.bond_count == 1 for component in dimers)
