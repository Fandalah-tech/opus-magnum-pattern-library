from packages.opus_engine import ArmState, Atom, Simulator, World


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
