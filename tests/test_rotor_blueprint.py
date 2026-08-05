from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from packages.opus_solver.rotor_blueprint import build_connected_rotor_blueprint


FIXTURE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")


def test_blueprint_uses_all_five_pulls_and_six_conversions() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    blueprint = build_connected_rotor_blueprint(puzzle)

    assert blueprint.supported is True
    assert blueprint.connected is True
    assert blueprint.transformation_count == 6
    assert {atom.pull_id for atom in blueprint.atoms} == {
        "r0-p0", "r0-p1", "r1-p0", "r1-p1", "r1-p2"
    }


def test_blueprint_consumes_each_reagent_pull_exactly_once() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    blueprint = build_connected_rotor_blueprint(puzzle)
    counts = Counter(atom.pull_id for atom in blueprint.atoms)

    assert counts == {
        "r0-p0": 2,
        "r0-p1": 2,
        "r1-p0": 3,
        "r1-p1": 3,
        "r1-p2": 3,
    }


def test_all_required_product_bonds_cross_pull_boundaries() -> None:
    puzzle = json.loads(FIXTURE.read_text(encoding="utf-8"))

    blueprint = build_connected_rotor_blueprint(puzzle)

    assert len(blueprint.pull_edges) == 6
    assert all(first != second for first, second in blueprint.pull_edges)
