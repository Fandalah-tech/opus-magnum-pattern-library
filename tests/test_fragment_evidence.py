from packages.opus_analysis import trace_fragment_evidence


def _molecule(kind):
    return {
        "id": kind,
        "atoms": [{"id": "a0", "element": "salt", "position": [0, 0]}],
        "bonds": [],
    }


def test_feed_fragment_is_confirmed_from_replay_spawn():
    puzzle = {
        "reagents": [_molecule("reagent-0")],
        "products": [],
    }
    solution = {
        "puzzleFile": "P001",
        "parts": [{
            "id": "input-0",
            "type": "input",
            "enabled": True,
            "position": [0, 0],
            "length": 1,
            "rotation": 0,
            "which": 0,
            "armNumber": 0,
            "program": [],
        }],
    }

    fragments = trace_fragment_evidence(puzzle, solution)
    feed = next(fragment for fragment in fragments if fragment["role"] == "feed")

    assert feed["evidence"]["level"] == "dynamic-confirmed"
    assert feed["evidence"]["sourceMoleculeCount"] == 1
    assert feed["evidence"]["glyphSimulationAvailable"] is False


def test_bonding_fragment_with_active_arm_is_marked_arm_observed_not_confirmed():
    puzzle = {"reagents": [], "products": []}
    solution = {
        "puzzleFile": "P001",
        "parts": [
            {
                "id": "arm-0",
                "type": "arm1",
                "enabled": True,
                "position": [0, 0],
                "length": 1,
                "rotation": 0,
                "which": 0,
                "armNumber": 1,
                "program": [{"cycle": 0, "instruction": "grab", "rawCode": "G"}],
            },
            {
                "id": "bonder-0",
                "type": "bonder",
                "enabled": True,
                "position": [1, 0],
                "length": 1,
                "rotation": 0,
                "which": 0,
                "armNumber": 0,
                "program": [],
            },
        ],
    }

    fragments = trace_fragment_evidence(puzzle, solution)
    bonding = next(fragment for fragment in fragments if fragment["role"] == "bonding")

    assert bonding["evidence"]["level"] == "dynamic-arm-observed"
    assert bonding["evidence"]["grabCount"] == 1
    assert bonding["evidence"]["glyphSimulationAvailable"] is False
