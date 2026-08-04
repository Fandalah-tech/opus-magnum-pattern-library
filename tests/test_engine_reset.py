from packages.opus_engine import ArmState, Atom, Simulator, World


def test_reset_releases_held_atom_before_returning_arm() -> None:
    world = World()
    world.add_atom(Atom("a", "fire", (1, 0)))
    arm = ArmState("arm", "arm1", (0, 0), 0, 1)
    simulator = Simulator(world, {"arm": arm})

    simulator.step({"arm": "grab"})
    assert arm.grabbing is True
    assert arm.held_atoms == {0: "a"}

    simulator.step({"arm": "reset"})

    assert arm.grabbing is False
    assert arm.held_atoms == {}
    assert world.atoms["a"].held_by == set()
    assert world.atoms["a"].position == (1, 0)
