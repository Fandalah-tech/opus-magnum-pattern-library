from packages.opus_engine import compare_replays


def test_compare_replays_matches_equivalent_observable_state() -> None:
    legacy = {
        "frames": [{
            "cycle": -1,
            "displayCycle": 0,
            "armStates": [{"partId": "arm", "origin": [0, 0], "rotation": 0, "length": 1, "grabbing": False}],
            "molecules": [{"atoms": [{"element": "salt", "position": [1, 0]}]}],
        }]
    }
    engine = {
        "frames": [{
            "cycle": 0,
            "arms": [{"partId": "arm", "origin": [0, 0], "rotation": 0, "length": 1, "grabbing": False}],
            "world": {"atoms": [{"id": "different-id", "element": "salt", "position": [1, 0]}]},
        }]
    }
    report = compare_replays(legacy, engine)
    assert report["status"] == "match"
    assert report["firstDivergence"] is None


def test_compare_replays_reports_first_atom_divergence() -> None:
    legacy = {"frames": [
        {"armStates": [], "molecules": [{"atoms": [{"element": "salt", "position": [0, 0]}]}]},
        {"armStates": [], "molecules": [{"atoms": [{"element": "salt", "position": [1, 0]}]}]},
    ]}
    engine = {"frames": [
        {"arms": [], "world": {"atoms": [{"element": "salt", "position": [0, 0]}]}},
        {"arms": [], "world": {"atoms": [{"element": "salt", "position": [0, 1]}]}},
    ]}
    report = compare_replays(legacy, engine)
    assert report["status"] == "diverged"
    assert report["firstDivergence"]["frameIndex"] == 1
    assert "atoms" in report["firstDivergence"]["categories"]


def test_compare_replays_prioritizes_engine_error_frame() -> None:
    legacy = {"frames": [
        {
            "displayCycle": 0,
            "armStates": [],
            "molecules": [],
            "events": [],
        },
        {
            "displayCycle": 1,
            "armStates": [{"partId": "arm", "origin": [0, 0], "rotation": 1, "length": 1, "grabbing": True}],
            "molecules": [{"atoms": [{"element": "salt", "position": [0, 1]}]}],
            "events": [{"kind": "arm-instruction", "partId": "arm", "instruction": "rotate_ccw"}],
        },
    ]}
    engine = {"frames": [
        {
            "cycle": 0,
            "phase": "initial",
            "arms": [],
            "world": {"atoms": []},
            "events": [],
        },
        {
            "cycle": 0,
            "phase": "error",
            "arms": [{"partId": "arm", "origin": [0, 0], "rotation": 0, "length": 1, "grabbing": True}],
            "world": {"atoms": [{"element": "salt", "position": [1, 0]}]},
            "events": [{"kind": "simulation-error", "cycle": 0, "message": "Motion collision at (0, 1)"}],
        },
    ]}

    report = compare_replays(legacy, engine)
    divergence = report["firstDivergence"]
    assert divergence["classification"]["subsystem"] == "engine-error"
    assert divergence["classification"]["reason"] == "simulation-error"
    assert divergence["classification"]["engineError"]["message"] == "Motion collision at (0, 1)"
