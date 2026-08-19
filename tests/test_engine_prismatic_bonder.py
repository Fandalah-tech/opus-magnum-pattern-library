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
        Bond("a", "b", "triplex-black").key,
        Bond("b", "c", "triplex-red").key,
        Bond("c", "a", "triplex-yellow").key,
    } <= set(world.bonds)
    assert sum(
        event["kind"] == "bond-created"
        and event.get("prismatic") is True
        and event.get("type") == "triplex"
        and event.get("triplexChannel") in {"red", "black", "yellow"}
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

    assert set(world.bonds) == {Bond("a", "b", "triplex-black").key}


def test_prismatic_bonder_can_add_a_second_channel_to_the_same_pair() -> None:
    puzzle = {"products": []}
    solution = {
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        ]
    }
    world = World()
    world.add_atom(Atom("a", "fire", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))
    world.add_bond(Bond("a", "b", "triplex-yellow"))
    simulator = Simulator.from_models(puzzle, solution)
    simulator.world = world

    simulator.step({})

    assert set(world.bonds) == {
        Bond("a", "b", "triplex-black").key,
        Bond("a", "b", "triplex-yellow").key,
    }


def test_prism_and_unbonder_follow_solution_part_order() -> None:
    puzzle = {"products": []}
    world = World()
    world.add_atom(Atom("a", "fire", (0, 0)))
    world.add_atom(Atom("b", "fire", (1, 0)))

    prism_first = Simulator.from_models(puzzle, {"parts": [
        {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
        {"id": "split", "type": "unbonder", "position": [0, 0], "rotation": 0},
    ]})
    prism_first.world = world
    prism_first.step({})

    assert set(world.bonds) == set()

    world.add_bond(Bond("a", "b", "normal"))
    unbonder_first = Simulator.from_models(puzzle, {"parts": [
        {"id": "split", "type": "unbonder", "position": [0, 0], "rotation": 0},
        {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
    ]})
    unbonder_first.world = world
    unbonder_first.step({})

    assert set(world.bonds) == {Bond("a", "b", "triplex-black").key}


def test_parser_triplex_mask_expands_for_inputs_and_outputs() -> None:
    molecule = {
        "atoms": [
            {"id": "a0", "element": "fire", "position": [0, 0]},
            {"id": "a1", "element": "fire", "position": [1, 0]},
        ],
        "bonds": [{
            "type": "triplex",
            "rawCode": 14,
            "triplexChannels": ["red", "black", "yellow"],
            "from": [0, 0],
            "to": [1, 0],
        }],
    }
    puzzle = {"reagents": [molecule], "products": [molecule]}
    solution = {
        "parts": [
            {"id": "input", "type": "input", "which": 0, "position": [0, 0], "rotation": 0},
            {"id": "output", "type": "out-std", "which": 0, "position": [0, 0], "rotation": 0},
        ]
    }

    simulator = Simulator.from_models(puzzle, solution)
    expected = {
        Bond("input-spawn-0-atom-0", "input-spawn-0-atom-1", "triplex-red").key,
        Bond("input-spawn-0-atom-0", "input-spawn-0-atom-1", "triplex-black").key,
        Bond("input-spawn-0-atom-0", "input-spawn-0-atom-1", "triplex-yellow").key,
    }

    assert set(simulator.world.bonds) == expected
    assert [bond[0] for bond in simulator.output_patterns[0][3]] == [
        "triplex-black",
        "triplex-red",
        "triplex-yellow",
    ]
