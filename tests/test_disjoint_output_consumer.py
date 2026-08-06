from packages.opus_engine.model import Atom, Bond
from packages.opus_engine.van_berlo_simulator import Simulator


def make_simulator():
    puzzle = {
        "products": [{
            "atoms": [
                {"position": [0, 0], "element": "fire"},
                {"position": [2, 0], "element": "water"},
                {"position": [3, 0], "element": "earth"},
            ],
            "bonds": [
                {"from": [2, 0], "to": [3, 0], "type": "normal"},
            ],
        }],
        "reagents": [],
    }
    solution = {
        "parts": [{
            "id": "output",
            "type": "out-std",
            "position": [5, -2],
            "rotation": 0,
            "which": 0,
        }],
    }
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world.add_atom(Atom("solo", "fire", (5, -2)))
    simulator.world.add_atom(Atom("pair-a", "water", (7, -2)))
    simulator.world.add_atom(Atom("pair-b", "earth", (8, -2)))
    simulator.world.add_bond(Bond("pair-a", "pair-b", "normal"))
    return simulator


def test_disjoint_product_is_delivered_as_one_output():
    simulator = make_simulator()
    simulator._process_consumers()
    assert simulator.delivered_products == {"output": 1}
    assert simulator.world.atoms == {}


def test_disjoint_product_rejects_extra_cross_component_bond():
    simulator = make_simulator()
    simulator.world.add_bond(Bond("solo", "pair-a", "normal"))
    simulator._process_consumers()
    assert simulator.delivered_products == {}
    assert set(simulator.world.atoms) == {"solo", "pair-a", "pair-b"}
