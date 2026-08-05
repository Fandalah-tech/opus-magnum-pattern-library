from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from packages.opus_solver import (
    UnsupportedPuzzleError,
    build_manufacturing_plan,
    solve_puzzle,
    validate_generated_solution,
)


def _stabilized_water_puzzle() -> dict:
    return {
        "schemaVersion": "0.1.0",
        "source": {"name": "P007.puzzle"},
        "name": "STABILIZED WATER",
        "availableParts": {
            "arms": ["arm1"],
            "glyphs": ["equilibrium", "bonder", "calcification"],
        },
        "reagents": [
            {"id": "reagent-0", "atoms": [{"id": "a0", "element": "water", "position": [0, 0]}], "bonds": []},
            {"id": "reagent-1", "atoms": [{"id": "a0", "element": "water", "position": [0, 0]}], "bonds": []},
        ],
        "products": [{
            "id": "product-0",
            "atoms": [
                {"id": "a0", "element": "salt", "position": [0, 0]},
                {"id": "a1", "element": "water", "position": [1, 0]},
            ],
            "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
        }],
        "outputScale": 1,
        "production": False,
    }


def test_manufacturing_plan_identifies_calcification_and_bonding() -> None:
    plan = build_manufacturing_plan(_stabilized_water_puzzle())

    assert plan.supported is True
    assert plan.strategy == "bonded-pair-v1"
    assert sorted(flow.transformation or "direct" for flow in plan.atom_flows) == [
        "calcification",
        "direct",
    ]
    assert [operation.kind for operation in plan.operations][-2:] == ["bond", "deliver"]
    assert plan.required_glyphs == ("bonder", "glyph-calcification")


def test_solver_generates_and_validates_six_products() -> None:
    puzzle = _stabilized_water_puzzle()
    result = solve_puzzle(puzzle)

    assert result.validation["complete"] is True
    assert result.validation["deliveredProducts"] == {"part-0": 6}
    assert result.solution["puzzleFile"] == "P007"
    assert result.solution["name"].startswith("Opus Solver MVP")
    assert result.solution["parts"][1]["position"] != [2, -2]


def test_generated_solution_round_trips_through_binary_format() -> None:
    puzzle = _stabilized_water_puzzle()
    generated = solve_puzzle(puzzle).solution

    encoded = write_solution_bytes(generated)
    parsed = parse_solution_bytes(encoded, source_name="P007-auto.solution")
    validation = validate_generated_solution(puzzle, parsed)

    assert parsed["format"]["version"] == 7
    assert parsed["puzzleFile"] == "P007"
    assert parsed["name"] == generated["name"]
    assert validation["complete"] is True
    assert validation["deliveredProducts"] == {"part-0": 6}


def test_solver_rejects_unsupported_product_shape() -> None:
    puzzle = _stabilized_water_puzzle()
    puzzle["products"][0]["atoms"].append(
        {"id": "a2", "element": "water", "position": [2, 0]}
    )

    try:
        solve_puzzle(puzzle)
    except UnsupportedPuzzleError as error:
        assert "exactly two atoms" in str(error)
    else:
        raise AssertionError("Unsupported puzzle should have raised UnsupportedPuzzleError")
