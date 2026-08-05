from packages.opus_engine import ArmState, Atom, Bond, Simulator, World


def make_disjoint_simulator() -> Simulator:
    world = World()
    world.add_atom(Atom("left", "salt", (1, 0)))
    world.add_atom(Atom("center", "salt", (3, 0)))
    world.add_atom(Atom("right", "salt", (5, 0)))
    simulator = Simulator(
        world,
        {
            "left-arm": ArmState("left-arm", "arm1", (0, 0), 0, 1),
            "center-arm": ArmState("center-arm", "arm1", (2, 0), 0, 1),
            "right-arm": ArmState("right-arm", "arm1", (4, 0), 0, 1),
        },
    )
    return simulator


def test_disconnected_atoms_remain_independent_mechanical_components() -> None:
    simulator = make_disjoint_simulator()

    assert simulator.molecule_atom_ids("left") == {"left"}
    assert simulator.molecule_atom_ids("center") == {"center"}
    assert simulator.molecule_atom_ids("right") == {"right"}


def test_grabbing_one_disjoint_component_does_not_move_the_others() -> None:
    simulator = make_disjoint_simulator()

    simulator.step({"left-arm": "grab"})
    simulator.step({"left-arm": "rotate_ccw"})

    assert simulator.world.atoms["left"].position == (0, 1)
    assert simulator.world.atoms["center"].position == (3, 0)
    assert simulator.world.atoms["right"].position == (5, 0)


def test_recent_bond_is_chemical_but_does_not_transmit_next_motion() -> None:
    world = World()
    world.add_atom(Atom("moving", "salt", (1, 0)))
    world.add_atom(Atom("stationary", "water", (2, 0)))
    bond = Bond("moving", "stationary")
    world.add_bond(bond)
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )
    simulator.floating_bond_roots[bond.key] = "stationary"

    assert bond.key in world.bonds
    assert simulator.molecule_atom_ids("moving") == {"moving"}
    assert simulator.molecule_atom_ids("stationary") == {"stationary"}

    simulator.step({"arm": "grab"})
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
