from packages.opus_engine.builder import InputSource
from packages.opus_engine.world import World


def test_disconnected_input_components_respawn_independently() -> None:
    source = InputSource(
        id="input-a",
        atom_templates=(("salt", (0, 0)), ("salt", (2, 0)), ("water", (4, 0))),
        bond_templates=(),
    )
    world = World()

    assert source.spawn(world)
    assert len(world.atoms) == 3
    assert source.spawn_count == 1

    world.remove_atom("input-a-spawn-0-atom-1")
    assert source.spawn(world)

    assert len(world.atoms) == 3
    assert "input-a-spawn-1-atom-1" in world.atoms
    assert "input-a-spawn-1-atom-0" not in world.atoms
    assert "input-a-spawn-1-atom-2" not in world.atoms
    assert source.spawn_count == 2


def test_bonded_input_component_waits_until_all_component_cells_are_clear() -> None:
    source = InputSource(
        id="input-b",
        atom_templates=(("water", (0, 0)), ("salt", (1, 0)), ("salt", (3, 0))),
        bond_templates=((0, 1, "normal"),),
    )
    world = World()

    assert source.spawn(world)
    world.remove_atom("input-b-spawn-0-atom-0")

    assert not source.spawn(world)
    assert "input-b-spawn-1-atom-0" not in world.atoms

    world.remove_atom("input-b-spawn-0-atom-1")
    assert source.spawn(world)
    assert "input-b-spawn-1-atom-0" in world.atoms
    assert "input-b-spawn-1-atom-1" in world.atoms
    assert "input-b-spawn-1-atom-2" not in world.atoms
