from packages.opus_engine.builder import InputSource
from packages.opus_engine.model import Bond
from packages.opus_engine.world import World


def test_disconnected_reagent_atoms_are_independent_molecules():
    world = World()
    source = InputSource(
        id="input",
        atom_templates=(("salt", (0, 0)), ("salt", (2, 0)), ("salt", (-2, 0))),
        bond_templates=(),
    )

    assert source.spawn(world)
    atom_ids = sorted(world.atoms)

    assert len(world.molecules()) == 3
    assert all(world.molecule_atom_ids(atom_id) == {atom_id} for atom_id in atom_ids)


def test_bonded_reagent_component_remains_one_molecule():
    world = World()
    source = InputSource(
        id="input",
        atom_templates=(("salt", (0, 0)), ("salt", (1, 0)), ("salt", (3, 0))),
        bond_templates=((0, 1, "normal"),),
    )

    assert source.spawn(world)
    first = "input-spawn-0-atom-0"
    second = "input-spawn-0-atom-1"
    third = "input-spawn-0-atom-2"

    assert Bond(first, second, "normal").key in world.bonds
    assert world.molecule_atom_ids(first) == {first, second}
    assert world.molecule_atom_ids(second) == {first, second}
    assert world.molecule_atom_ids(third) == {third}
