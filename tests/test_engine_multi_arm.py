from packages.opus_engine import ArmState, Atom, SimulationError, Simulator, World


def test_arm2_exposes_opposed_tips() -> None:
    arm = ArmState("arm", "arm2", (0, 0), 0, 1)
    assert arm.tips() == {0: (1, 0), 1: (-1, 0)}


def test_arm3_exposes_three_evenly_spaced_tips() -> None:
    arm = ArmState("arm", "arm3", (0, 0), 0, 1)
    assert set(arm.tips().values()) == {(1, 0), (-1, 1), (0, -1)}


def test_arm2_grabs_and_rotates_both_atoms() -> None:
    world = World()
    world.add_atom(Atom("right", "salt", (1, 0)))
    world.add_atom(Atom("left", "water", (-1, 0)))
    arm = ArmState("arm", "arm2", (0, 0), 0, 1)
    simulator = Simulator(world, {"arm": arm})

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "rotate_ccw"})

    assert set(arm.held_atoms.values()) == {"right", "left"}
    assert world.atoms["right"].position == (0, 1)
    assert world.atoms["left"].position == (0, -1)


def test_repeated_grab_does_not_fill_free_multiarm_branch() -> None:
    world = World()
    world.add_atom(Atom("first", "salt", (1, 0)))
    arm = ArmState("arm", "arm2", (0, 0), 0, 1)
    simulator = Simulator(world, {"arm": arm})
    simulator.step({"arm": "grab"})
    world.add_atom(Atom("later", "water", (-1, 0)))
    simulator.step({"arm": "grab"})
    assert set(arm.held_atoms.values()) == {"first"}
    assert not world.atoms["later"].held_by


def test_shared_atom_rotations_need_same_physical_transform() -> None:
    world = World()
    world.add_atom(Atom("shared", "salt", (0, 0)))
    first = ArmState("first", "arm1", (-1, 0), 0, 1)
    second = ArmState("second", "arm1", (0, -1), 1, 1)
    first.grabbing = second.grabbing = True
    first.held_atoms[0] = second.held_atoms[0] = "shared"
    world.atoms["shared"].held_by.update({"first", "second"})
    simulator = Simulator(world, {"first": first, "second": second})
    try:
        simulator.step({"first": "rotate_ccw", "second": "rotate_cw"})
    except SimulationError as error:
        assert "motions" in str(error)
    else:
        raise AssertionError("Different physical rotations must not be merged")
