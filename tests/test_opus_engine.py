from packages.opus_engine import (
    ArmState,
    Atom,
    Bond,
    SimulationError,
    Simulator,
    World,
    connected_components,
)


def test_connected_components_split_after_unbond() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    world.add_atom(Atom("b", "salt", (1, 0)))
    world.add_atom(Atom("c", "water", (4, 0)))
    world.add_bond(Bond("a", "b"))

    assert sorted(len(item.atom_ids) for item in world.molecules()) == [1, 2]
    world.remove_bond("a", "b")
    assert sorted(len(item.atom_ids) for item in world.molecules()) == [1, 1, 1]


def test_world_rejects_atom_collision() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    try:
        world.add_atom(Atom("b", "water", (0, 0)))
    except ValueError as error:
        assert "already occupied" in str(error)
    else:
        raise AssertionError("Expected occupied hex to be rejected")


def test_connected_components_accepts_isolated_atoms() -> None:
    assert sorted(connected_components(["a", "b"], [])) == [{"a"}, {"b"}]


def test_arm6_exposes_six_tips() -> None:
    arm = ArmState("arm", "arm6", (0, 0), 0, 1)
    assert set(arm.tips().values()) == {(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)}


def test_simulator_grabs_and_rotates_connected_molecule() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (1, 0)))
    world.add_atom(Atom("b", "water", (2, 0)))
    world.add_bond(Bond("a", "b"))
    simulator = Simulator(world, {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)})

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "rotate_ccw"})

    assert world.atoms["a"].position == (0, 1)
    assert world.atoms["b"].position == (0, 2)
    assert simulator.arms["arm"].rotation == 1


def test_simulator_rejects_collision_transactionally() -> None:
    world = World()
    world.add_atom(Atom("moving", "salt", (1, 0)))
    world.add_atom(Atom("blocking", "water", (0, 1)))
    simulator = Simulator(world, {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)})
    simulator.step({"arm": "grab"})

    try:
        simulator.step({"arm": "rotate_ccw"})
    except SimulationError as error:
        assert "collides" in str(error)
    else:
        raise AssertionError("Expected collision to reject the cycle")

    assert world.atoms["moving"].position == (1, 0)
    assert simulator.arms["arm"].rotation == 0


def test_piston_moves_held_molecule() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (1, 0)))
    arm = ArmState("arm", "piston", (0, 0), 0, 1)
    simulator = Simulator(world, {"arm": arm})

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "extend"})

    assert arm.length == 2
    assert world.atoms["a"].position == (2, 0)


def test_pivot_rotates_around_grabbed_atom() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (1, 0)))
    world.add_atom(Atom("b", "water", (2, 0)))
    world.add_bond(Bond("a", "b"))
    simulator = Simulator(world, {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)})

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "pivot_ccw"})

    assert world.atoms["a"].position == (1, 0)
    assert world.atoms["b"].position == (1, 1)


def test_track_move_translates_arm_and_molecule() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (1, 0)))
    arm = ArmState("arm", "arm1", (0, 0), 0, 1, track_cells=((0, 0), (1, 0)))
    simulator = Simulator(world, {"arm": arm})

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "track_plus"})

    assert arm.origin == (1, 0)
    assert world.atoms["a"].position == (2, 0)
