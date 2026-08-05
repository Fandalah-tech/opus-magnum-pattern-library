from packages.opus_engine import ArmState, Atom, Bond, Simulator, World
from packages.opus_solver.state import canonical_state_key


def _simulator(atom_prefix: str = "atom") -> Simulator:
    world = World()
    world.add_atom(Atom(f"{atom_prefix}-left", "salt", (1, 0)))
    world.add_atom(Atom(f"{atom_prefix}-center", "salt", (3, 0)))
    world.add_atom(Atom(f"{atom_prefix}-right", "water", (5, 0)))
    return Simulator(
        world,
        {
            "arm": ArmState("arm", "arm1", (0, 0), 0, 1),
        },
    )


def test_state_key_ignores_atom_identifier_names() -> None:
    assert canonical_state_key(_simulator("first")) == canonical_state_key(_simulator("second"))


def test_state_key_distinguishes_disjoint_component_position() -> None:
    first = _simulator()
    second = _simulator()
    second.world.atoms["atom-right"].position = (4, 1)

    assert canonical_state_key(first) != canonical_state_key(second)


def test_state_key_distinguishes_recent_bond_from_physical_bond() -> None:
    physical = _simulator()
    recent = _simulator()
    physical_bond = Bond("atom-left", "atom-center")
    recent_bond = Bond("atom-left", "atom-center")
    physical.world.add_bond(physical_bond)
    recent.world.add_bond(recent_bond)
    recent.floating_bond_roots[recent_bond.key] = "atom-center"

    assert canonical_state_key(physical) != canonical_state_key(recent)


def test_state_key_distinguishes_which_disjoint_atom_is_held() -> None:
    first = _simulator()
    second = _simulator()

    first.arms["arm"].grabbing = True
    first.arms["arm"].held_atoms[0] = "atom-left"
    first.world.atoms["atom-left"].held_by.add("arm")

    second.arms["arm"].grabbing = True
    second.arms["arm"].held_atoms[0] = "atom-center"
    second.world.atoms["atom-center"].held_by.add("arm")

    assert canonical_state_key(first) != canonical_state_key(second)


def test_equivalent_recent_bond_states_ignore_atom_identifiers() -> None:
    first = _simulator("first")
    second = _simulator("second")
    first_bond = Bond("first-left", "first-center")
    second_bond = Bond("second-left", "second-center")
    first.world.add_bond(first_bond)
    second.world.add_bond(second_bond)
    first.floating_bond_roots[first_bond.key] = "first-center"
    second.floating_bond_roots[second_bond.key] = "second-center"

    assert canonical_state_key(first) == canonical_state_key(second)
