from packages.opus_engine import Atom, Bond, World, connected_components


def test_connected_components_split_after_unbond() -> None:
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    world.add_atom(Atom("b", "salt", (1, 0)))
    world.add_atom(Atom("c", "water", (4, 0)))
    world.add_bond(Bond("a", "b"))

    molecules = world.molecules()
    assert sorted(len(item.atom_ids) for item in molecules) == [1, 2]

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
