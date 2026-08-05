from packages.opus_engine import Atom, Bond, Simulator, World


def test_prismatic_bonder_creates_triangle_bonds() -> None:
    puzzle = {"products": []}
    solution = {
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        ]
    }
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))
    world.add_atom(Atom("c", "water", (0, 1)))
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world = world

    frame = simulator.step({})

    assert {
        Bond("a", "b").key,
        Bond("b", "c").key,
        Bond("c", "a").key,
    } <= set(world.bonds)
    assert sum(
        event["kind"] == "bond-created" and event.get("prismatic") is True
        for event in frame["events"]
    ) == 3


def test_prismatic_bonder_waits_for_all_three_atoms() -> None:
    puzzle = {"products": []}
    solution = {
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        ]
    }
    world = World()
    world.add_atom(Atom("a", "salt", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world = world

    simulator.step({})

    assert world.bonds == {}
