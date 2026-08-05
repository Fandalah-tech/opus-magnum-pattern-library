from types import SimpleNamespace

from packages.opus_engine import Atom, Bond, World
from packages.opus_solver.structure_goal import StructureGoal


def _product() -> dict:
    return {
        "atoms": [
            {"id": "a", "element": "salt", "position": [0, 0]},
            {"id": "b", "element": "water", "position": [1, 0]},
            {"id": "c", "element": "fire", "position": [0, 1]},
        ],
        "bonds": [
            {"type": "normal", "from": [0, 0], "to": [1, 0]},
        ],
    }


def _simulator(rotated: bool = False) -> SimpleNamespace:
    world = World()
    positions = [(0, 0), (0, 1), (-1, 1)] if rotated else [(4, -2), (5, -2), (4, -1)]
    for index, position in enumerate(positions):
        world.add_atom(Atom(str(index), "quintessence", position))
    world.add_bond(Bond("0", "1"))
    return SimpleNamespace(world=world)


def test_structure_goal_ignores_elements_translation_and_rotation() -> None:
    goal = StructureGoal.from_product(_product())
    assert goal.reached(_simulator())
    assert goal.reached(_simulator(rotated=True))


def test_structure_goal_rejects_missing_bond() -> None:
    simulator = _simulator()
    simulator.world.remove_bond("0", "1")
    goal = StructureGoal.from_product(_product())
    assert not goal.reached(simulator)
