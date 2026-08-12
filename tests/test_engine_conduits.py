from packages.opus_engine import Atom, Bond, Simulator


def _simulator(*, target_rotation: int = 0) -> Simulator:
    return Simulator.from_models({"products": []}, {"parts": [
        {"id": "pipe-a", "type": "pipe", "pipeId": 7, "position": [0, 0], "rotation": 0,
         "pipeHexes": [[0, 0], [1, 0]]},
        {"id": "pipe-b", "type": "pipe", "pipeId": 7, "position": [5, 0], "rotation": target_rotation,
         "pipeHexes": [[0, 0], [1, 0]]},
    ]})


def test_conduit_transports_whole_bonded_molecule() -> None:
    simulator = _simulator()
    simulator.world.add_atom(Atom("a", "salt", (0, 0)))
    simulator.world.add_atom(Atom("b", "water", (1, 0)))
    simulator.world.add_bond(Bond("a", "b"))
    frame = simulator.step({})
    assert sorted((atom.element, atom.position) for atom in simulator.world.atoms.values()) == [
        ("salt", (5, 0)), ("water", (6, 0)),
    ]
    assert len(simulator.world.bonds) == 1
    assert any(event["kind"] == "molecule-entered-conduit" for event in frame["events"])
    assert any(event["kind"] == "molecule-exited-conduit" for event in frame["events"])


def test_conduit_rotates_payload_with_target() -> None:
    simulator = _simulator(target_rotation=1)
    simulator.world.add_atom(Atom("a", "salt", (0, 0)))
    simulator.world.add_atom(Atom("b", "water", (1, 0)))
    simulator.world.add_bond(Bond("a", "b"))
    simulator.step({})
    assert {atom.position for atom in simulator.world.atoms.values()} == {(5, 0), (5, 1)}


def test_conduit_ignores_molecule_not_fully_inside_footprint() -> None:
    simulator = _simulator()
    simulator.world.add_atom(Atom("a", "salt", (1, 0)))
    simulator.world.add_atom(Atom("b", "water", (2, 0)))
    simulator.world.add_bond(Bond("a", "b"))
    simulator.step({})
    assert {atom.id for atom in simulator.world.atoms.values()} == {"a", "b"}
