from packages.opus_engine import Atom, Bond, Simulator, World


def test_prismatic_bonder_creates_triplex_bonds_between_fire_pairs() -> None:
    puzzle = {"products": []}
    solution = {
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        ]
    }
    world = World()
    world.add_atom(Atom("a", "fire", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))
    world.add_atom(Atom("c", "fire", (0, 1)))
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world = world

    frame = simulator.step({})

    assert {
        Bond("a", "b", "triplex").key,
        Bond("b", "c", "triplex").key,
        Bond("c", "a", "triplex").key,
    } <= set(world.bonds)
    assert sum(
        event["kind"] == "bond-created"
        and event.get("prismatic") is True
        and event.get("type") == "triplex"
        for event in frame["events"]
    ) == 3


def test_prismatic_bonder_only_bonds_present_fire_pairs() -> None:
    puzzle = {"products": []}
    solution = {
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        ]
    }
    world = World()
    world.add_atom(Atom("a", "fire", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world = world

    simulator.step({})

    assert set(world.bonds) == {Bond("a", "b", "triplex").key}
