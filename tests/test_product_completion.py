from packages.opus_engine.builder import rotate_hex
from packages.opus_solver.product_completion import (
    ProductCore,
    find_persistent_product_core,
    materialize_repeating_product_completion,
    materialize_single_product_completion,
    reorder_instantaneous_bonders,
    search_repeating_product_completions,
    search_single_product_completions,
)


CHANNELS = ("black", "red", "yellow")


def _core_frame(cycle: int):
    atoms = [
        {"id": "end", "element": "fire", "position": [-5, 3]},
        {"id": "middle", "element": "fire", "position": [-4, 2]},
        {"id": "salt", "element": "salt", "position": [-3, 1]},
    ]
    bonds = [
        {"fromAtomId": first, "toAtomId": second, "type": f"triplex-{channel}"}
        for first, second in (("end", "middle"), ("middle", "salt"))
        for channel in CHANNELS
    ]
    return {
        "cycle": cycle,
        "world": {
            "atoms": atoms,
            "bonds": bonds,
            "molecules": [{"atomIds": ["end", "middle", "salt"]}],
        },
        "events": [],
    }


def test_finds_only_a_persistent_complete_three_atom_product_core():
    replay = {"frames": [_core_frame(52), _core_frame(53), _core_frame(54)]}

    core = find_persistent_product_core(replay, persistence_frames=2)

    assert core == ProductCore(
        cycle=52,
        endpoint=(-5, 3),
        neighbor=(-4, 2),
        atom_ids=("end", "middle", "salt"),
    )


def test_materializes_the_oracle_proven_completion_template():
    source = {
        "puzzleFile": "heldout.puzzle",
        "parts": [
            {"id": "prism", "type": "bonder-prisma", "position": [0, 0], "rotation": 0},
            {"id": "split", "type": "unbonder", "position": [1, 0], "rotation": 0},
            {"id": "output", "type": "out-std", "position": [9, 9], "rotation": 0, "which": 0},
        ],
    }
    core = ProductCore(53, (-5, 3), (-4, 2), ("end", "middle", "salt"))

    solution = materialize_single_product_completion(source, core)
    parts = {part["id"]: part for part in solution["parts"]}

    assert [part["type"] for part in solution["parts"][:2]] == ["unbonder", "unbonder"]
    assert parts["fire-supply-input"]["position"] == [-6, 5]
    assert parts["fire-supply-arm"]["position"] == [-7, 4]
    assert parts["fire-supply-arm"]["program"] == [
        {"cycle": 55, "instruction": "grab"},
        {"cycle": 56, "instruction": "rotate_cw"},
        {"cycle": 57, "instruction": "drop"},
    ]
    assert parts["final-red-arm"]["program"][-1]["cycle"] == 60
    assert parts["output"]["position"] == [-5, 2]
    assert parts["output"]["rotation"] == 4


def test_completion_template_rotates_with_the_detected_core():
    steps = 2
    core = ProductCore(
        20,
        rotate_hex((-5, 3), steps),
        rotate_hex((-4, 2), steps),
        ("end", "middle", "salt"),
    )
    source = {"parts": [{"id": "output", "type": "out-std", "which": 0}]}

    solution = materialize_single_product_completion(source, core)
    parts = {part["id"]: part for part in solution["parts"]}

    assert parts["fire-supply-input"]["position"] == list(rotate_hex((-6, 5), steps))
    assert parts["fire-supply-arm"]["rotation"] == (1 + steps) % 6
    assert parts["output"]["position"] == list(rotate_hex((-5, 2), steps))
    assert parts["output"]["rotation"] == (4 + steps) % 6


def test_reordering_is_stable_within_each_glyph_family():
    solution = {"parts": [
        {"id": "p1", "type": "bonder-prisma"},
        {"id": "arm", "type": "arm1"},
        {"id": "u1", "type": "unbonder"},
        {"id": "p2", "type": "bonder-prisma"},
        {"id": "u2", "type": "unbonder"},
    ]}

    ordered = reorder_instantaneous_bonders(solution)

    assert [part["id"] for part in ordered["parts"]] == ["u1", "u2", "p1", "p2", "arm"]
    assert [part["id"] for part in solution["parts"]] == ["p1", "arm", "u1", "p2", "u2"]


def test_search_promotes_only_a_local_delivery_to_the_product_oracle(monkeypatch):
    source_replay = {"frames": [_core_frame(53), _core_frame(54)]}
    delivered_replay = {"frames": [{
        "cycle": 59,
        "events": [{"kind": "product-delivered", "cycle": 59}],
        "world": {"atoms": [], "bonds": [], "molecules": []},
    }]}
    replays = iter((source_replay, delivered_replay))
    monkeypatch.setattr(
        "packages.opus_solver.product_completion._run_replay",
        lambda *args, **kwargs: next(replays),
    )
    source = {
        "puzzleFile": "heldout",
        "parts": [{
            "id": "output",
            "type": "out-std",
            "position": [0, 0],
            "rotation": 0,
            "which": 0,
            "program": [],
        }],
    }

    result = search_single_product_completions(
        {"products": [], "reagents": []},
        [{"solution": source}],
        product_oracle_validator=lambda solution: {
            "status": "product-complete",
            "valid": True,
            "value": 61,
        },
        oracle_workers=99,
    )

    assert result["summary"] == {
        "searchedSourceCount": 1,
        "persistentProductCoreCount": 1,
        "generatedCompletionCount": 1,
        "localSingleProductCompleteCount": 1,
        "oraclePromotedCount": 1,
        "oracleSingleProductCompleteCount": 1,
        "hasOracleSingleProduct": True,
        "bestSingleProductCycle": 61,
        "oracleOutcomeCounts": {"product-complete": 1},
    }


def test_repeating_completion_reuses_all_three_auxiliary_atoms():
    core = ProductCore(53, (-5, 3), (-4, 2), ("end", "middle", "salt"))
    source = {
        "puzzleFile": "heldout",
        "parts": [
            {
                "id": "producer",
                "type": "piston",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 53, "instruction": "drop"},
                ],
            },
            {
                "id": "output",
                "type": "out-std",
                "position": [0, 0],
                "rotation": 0,
                "which": 0,
                "program": [],
            },
        ],
    }
    one_shot = materialize_single_product_completion(source, core)

    solution = materialize_repeating_product_completion(one_shot, core)
    parts = {part["id"]: part for part in solution["parts"]}

    assert parts["fire-supply-second-unbonder"]["position"] == [-6, 5]
    assert parts["fire-supply-duplication"]["position"] == [-6, 5]
    assert parts["fire-supply-track"]["trackHexes"] == [[0, 0], [1, 0], [2, 0]]
    assert parts["producer"]["program"][-1] == {
        "cycle": 162,
        "instruction": "reset",
    }
    assert parts["fire-supply-arm"]["program"][5] == {
        "cycle": 109,
        "instruction": "grab",
    }
    assert parts["fire-supply-arm"]["program"][12] == {
        "cycle": 163,
        "instruction": "grab",
    }
    assert [
        item["cycle"] for item in parts["final-red-arm"]["program"]
        if item["instruction"] == "grab"
    ] == [58, 112, 166]


def test_repeating_supply_track_rotates_with_the_product_core():
    steps = 2
    core = ProductCore(
        10,
        rotate_hex((-5, 3), steps),
        rotate_hex((-4, 2), steps),
        ("end", "middle", "salt"),
    )
    source = {
        "parts": [
            {
                "id": "producer",
                "type": "piston",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 10, "instruction": "drop"},
                ],
            },
            {"id": "output", "type": "out-std", "which": 0, "program": []},
        ],
    }
    one_shot = materialize_single_product_completion(source, core)

    solution = materialize_repeating_product_completion(one_shot, core)
    track = next(part for part in solution["parts"] if part["id"] == "fire-supply-track")
    step = rotate_hex((1, 0), steps)

    assert track["trackHexes"] == [[0, 0], list(step), [2 * step[0], 2 * step[1]]]


def test_repeating_search_requires_six_local_and_six_oracle_products(monkeypatch):
    monkeypatch.setattr(
        "packages.opus_solver.product_completion._run_replay",
        lambda *args, **kwargs: {
            "frames": [{
                "cycle": cycle,
                "events": [{"kind": "product-delivered", "cycle": cycle}],
                "world": {"atoms": [], "bonds": [], "molecules": []},
            } for cycle in (60, 119, 178, 237, 296, 355)],
        },
    )
    core = ProductCore(53, (-5, 3), (-4, 2), ("end", "middle", "salt"))
    source = {
        "puzzleFile": "heldout",
        "parts": [
            {
                "id": "producer",
                "type": "piston",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "which": 0,
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 53, "instruction": "drop"},
                ],
            },
            {
                "id": "output",
                "type": "out-std",
                "position": [0, 0],
                "rotation": 0,
                "which": 0,
                "program": [],
            },
        ],
    }
    one_shot = materialize_single_product_completion(source, core)

    result = search_repeating_product_completions(
        {"products": [], "reagents": []},
        [{"solution": one_shot, "core": {
            "cycle": core.cycle,
            "endpoint": list(core.endpoint),
            "neighbor": list(core.neighbor),
            "atom_ids": list(core.atom_ids),
        }}],
        full_product_oracle_validator=lambda solution: {
            "status": "product-complete",
            "valid": True,
            "productCount": 6,
            "value": 356,
        },
        oracle_workers=10,
    )

    assert result["summary"] == {
        "searchedSourceCount": 1,
        "generatedRepeatingCompletionCount": 1,
        "localFullProductCompleteCount": 1,
        "oraclePromotedCount": 1,
        "oracleFullProductCompleteCount": 1,
        "hasOracleFullPuzzle": True,
        "bestFullProductCycle": 356,
        "oracleOutcomeCounts": {"product-complete": 1},
    }
