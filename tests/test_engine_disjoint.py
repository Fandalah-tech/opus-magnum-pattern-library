from packages.opus_engine import ArmState, Atom, Bond, Simulator, World


def make_disjoint_simulator() -> Simulator:
    world = World()
    world.add_atom(Atom("left", "salt", (1, 0)))
    world.add_atom(Atom("center", "salt", (3, 0)))
    world.add_atom(Atom("right", "salt", (5, 0)))
    world.register_molecule({"left", "center", "right"}, "tripartite-salt")
    return Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )


def test_disconnected_atoms_share_one_logical_mechanical_molecule() -> None:
    simulator = make_disjoint_simulator()

    expected = {"left", "center", "right"}
    assert simulator.molecule_atom_ids("left") == expected
    assert simulator.molecule_atom_ids("center") == expected
    assert simulator.molecule_atom_ids("right") == expected


def test_grabbing_one_disjoint_part_moves_the_whole_logical_molecule() -> None:
    simulator = make_disjoint_simulator()

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "rotate_ccw"})

    assert simulator.world.atoms["left"].position == (0, 1)
    assert simulator.world.atoms["center"].position == (0, 3)
    assert simulator.world.atoms["right"].position == (0, 5)


def test_successful_debond_recalculates_all_disjoint_components() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    world.add_atom(Atom("b", "water", (1, 0)))
    world.add_atom(Atom("remote", "salt", (4, 0)))
    world.add_bond(Bond("a", "b"))
    world.register_molecule({"a", "b", "remote"}, "disjoint-reagent")

    assert world.molecule_atom_ids("a") == {"a", "b", "remote"}
    assert world.remove_bond("a", "b") is True

    assert world.molecule_atom_ids("a") == {"a"}
    assert world.molecule_atom_ids("b") == {"b"}
    assert world.molecule_atom_ids("remote") == {"remote"}


def test_recent_bond_is_chemical_but_does_not_transmit_its_motion_half_cycle() -> None:
    world = World()
    world.add_atom(Atom("moving", "salt", (1, 0)))
    world.add_atom(Atom("stationary", "water", (2, 0)))
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )

    # The arm must already be holding the payload when the first-half bonder
    # phase creates a recent bond. A separate grab cycle would consume the
    # recent-bond lifetime before the physical rotation being tested.
    simulator.step({"arm": "grab"})
    bond = Bond("moving", "stationary")
    world.add_bond(bond)
    simulator.floating_bond_roots[bond.key] = "stationary"

    assert bond.key in world.bonds
    assert simulator.molecule_atom_ids("moving") == {"moving"}
    assert simulator.molecule_atom_ids("stationary") == {"stationary"}

    simulator.step({"arm": "rotate_ccw"})

    assert world.atoms["moving"].position == (0, 1)
    assert world.atoms["stationary"].position == (2, 0)
    assert bond.key not in world.bonds
    assert bond.key not in simulator.floating_bond_roots


def test_normal_bond_transmits_motion_after_recent_flag_is_gone() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (1, 0)))
    world.add_atom(Atom("b", "water", (2, 0)))
    bond = Bond("a", "b")
    world.add_bond(bond)
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )

    assert simulator.molecule_atom_ids("a") == {"a", "b"}

    simulator.step({"arm": "grab"})
    simulator.step({"arm": "rotate_ccw"})

    assert world.atoms["a"].position == (0, 1)
    assert world.atoms["b"].position == (0, 2)
