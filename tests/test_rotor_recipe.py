from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_recipe import build_rotor_recipe


FIXTURE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")


def test_rotor_recipe_uses_exact_five_reagent_pulls() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    recipe = build_rotor_recipe(puzzle)

    assert recipe.supported is True
    assert recipe.reagent_pulls == (2, 3)
    assert len(recipe.assignments) == 13
    assert len({
        (assignment.source.pull_id, assignment.source.atom_index)
        for assignment in recipe.assignments
    }) == 13
    assert len({assignment.target.atom_id for assignment in recipe.assignments}) == 13


def test_rotor_recipe_requires_exactly_six_van_berlo_transmutations() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    recipe = build_rotor_recipe(puzzle)

    assert recipe.transformation_count == 6
    assert sum(
        assignment.transformation == "van-berlo"
        for assignment in recipe.assignments
    ) == 6


def test_rotor_recipe_covers_all_product_components() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    recipe = build_rotor_recipe(puzzle)
    component_indexes = {
        assignment.target.component_index
        for assignment in recipe.assignments
    }

    assert component_indexes == set(range(7))
    assert set(recipe.preserved_components) | set(recipe.mixed_components) == component_indexes
    assert set(recipe.preserved_components).isdisjoint(recipe.mixed_components)


def test_rotor_recipe_rejects_wrong_pull_count() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    recipe = build_rotor_recipe(puzzle, reagent_pulls=(1, 3))

    assert recipe.supported is False
    assert "does not match product atom count" in str(recipe.reason)
