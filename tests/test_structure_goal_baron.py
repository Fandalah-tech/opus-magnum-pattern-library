from types import SimpleNamespace

from packages.opus_engine import ArmState, Atom, World
from packages.opus_solver import StructureGoal


def _simulator_with_baron_atom():
    world = World()
    atom = Atom("wheel", "salt", (0, 0))
    atom.held_by.add("baron")
    world.add_atom(atom)
    return SimpleNamespace(
        world=world,
        arms={"baron": ArmState("baron", "baron", (0, 0), 0, 1)},
    )


def test_structure_goal_excludes_baron_atoms_by_default():
    goal = StructureGoal.from_product({"atoms": [{"position": [0, 0]}], "bonds": []})
    assert goal.best_match(_simulator_with_baron_atom()).occupied_positions == 0


def test_structure_goal_can_include_baron_atoms_for_rotor_checkpoint():
    goal = StructureGoal.from_product(
        {"atoms": [{"position": [0, 0]}], "bonds": []},
        include_baron_held=True,
    )
    assert goal.best_match(_simulator_with_baron_atom()).occupied_positions == 1
