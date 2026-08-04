from packages.opus_engine import Simulator


def test_output_consumes_product_before_input_respawn() -> None:
    puzzle = {
        "reagents": [{"atoms": [{"element": "water", "position": [0, 0]}], "bonds": []}],
        "products": [{"atoms": [{"element": "water", "position": [0, 0]}], "bonds": []}],
    }
    solution = {
        "parts": [
            {"id": "input", "type": "input", "which": 0, "position": [1, 0], "rotation": 0},
            {"id": "output", "type": "out-std", "which": 0, "position": [0, 1], "rotation": 0},
            {"id": "arm", "type": "arm1", "position": [0, 0], "rotation": 0, "length": 1},
        ]
    }
    simulator = Simulator.from_models(puzzle, solution)

    simulator.step({"arm": "grab"})
    frame = simulator.step({"arm": "rotate_ccw"})

    assert sorted((atom.element, atom.position) for atom in simulator.world.atoms.values()) == [
        ("water", (1, 0)),
    ]
    assert simulator.delivered_products == {"output": 1}
    assert any(event["kind"] == "product-delivered" for event in frame["events"])


def test_held_product_is_not_consumed() -> None:
    puzzle = {
        "reagents": [{"atoms": [{"element": "salt", "position": [0, 0]}], "bonds": []}],
        "products": [{"atoms": [{"element": "salt", "position": [0, 0]}], "bonds": []}],
    }
    solution = {
        "parts": [
            {"id": "input", "type": "input", "which": 0, "position": [1, 0], "rotation": 0},
            {"id": "output", "type": "out-std", "which": 0, "position": [1, 0], "rotation": 0},
            {"id": "arm", "type": "arm1", "position": [0, 0], "rotation": 0, "length": 1},
        ]
    }
    simulator = Simulator.from_models(puzzle, solution)

    simulator.step({"arm": "grab"})

    assert len(simulator.world.atoms) == 1
    assert simulator.delivered_products == {}
