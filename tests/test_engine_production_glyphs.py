from packages.opus_engine import Atom, Bond, Simulator, World


def _simulator(part_type: str, *, rotation: int = 0) -> Simulator:
    return Simulator.from_models(
        {"products": []},
        {"parts": [{"id": "glyph", "type": part_type, "position": [0, 0], "rotation": rotation}]},
    )


def test_world_exposes_deterministic_top_atom() -> None:
    world = World()
    world.add_atom(Atom("bottom", "salt", (0, 0)))
    world.add_overlapped_atom(Atom("top", "fire", (0, 0)))
    assert [atom.id for atom in world.atoms_at((0, 0))] == ["bottom", "top"]
    assert world.atom_at((0, 0)).id == "top"
    world.remove_atom("top")
    assert world.atom_at((0, 0)).id == "bottom"


def test_multi_bonder_creates_three_center_bonds() -> None:
    simulator = _simulator("bonder-speed")
    simulator.world.add_atom(Atom("center", "salt", (0, 0)))
    for atom_id, position in (("east", (1, 0)), ("south", (0, -1)), ("northwest", (-1, 1))):
        simulator.world.add_atom(Atom(atom_id, "salt", position))
    simulator.step({})
    assert {bond.key for bond in simulator.world.bonds.values()} == {
        Bond("center", "east").key,
        Bond("center", "south").key,
        Bond("center", "northwest").key,
    }


def test_rejection_degrades_metal_and_emits_quicksilver() -> None:
    simulator = _simulator("glyph-rejection")
    simulator.world.add_atom(Atom("metal", "silver", (0, 0)))
    simulator.step({})
    assert simulator.world.atoms["metal"].element == "copper"
    assert simulator.world.atom_at((1, 0)).element == "quicksilver"


def test_division_splits_gold_into_two_iron_atoms() -> None:
    simulator = _simulator("glyph-division")
    simulator.world.add_atom(Atom("metal", "gold", (0, 0)))
    simulator.step({})
    assert simulator.world.atom_at((1, 0)).element == "iron"
    assert simulator.world.atom_at((-1, 0)).element == "iron"
    assert "metal" not in simulator.world.atoms


def test_unification_consumes_four_elements() -> None:
    simulator = _simulator("glyph-unification")
    for atom_id, element, position in (
        ("air", "air", (0, 1)),
        ("earth", "earth", (-1, 1)),
        ("fire", "fire", (0, -1)),
        ("water", "water", (1, -1)),
    ):
        simulator.world.add_atom(Atom(atom_id, element, position))
    simulator.step({})
    assert simulator.world.atom_at((0, 0)).element == "quintessence"
    assert len(simulator.world.atoms) == 1


def test_proliferation_consumes_unbonded_quicksilver() -> None:
    simulator = _simulator("glyph-proliferation")
    simulator.world.add_atom(Atom("source", "copper", (-1, 1)))
    simulator.world.add_atom(Atom("q", "quicksilver", (1, 1)))
    simulator.step({})
    assert simulator.world.atom_at((1, -1)).element == "copper"
    assert "q" not in simulator.world.atoms


def test_division_rejects_bonded_input() -> None:
    simulator = _simulator("glyph-division")
    simulator.world.add_atom(Atom("metal", "gold", (0, 0)))
    simulator.world.add_atom(Atom("other", "salt", (0, 1)))
    simulator.world.add_bond(Bond("metal", "other"))
    simulator.step({})
    assert simulator.world.atoms["metal"].element == "gold"
    assert simulator.world.atom_at((1, 0)) is None
