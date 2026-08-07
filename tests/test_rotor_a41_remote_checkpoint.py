from __future__ import annotations

import json

import tools.run_rotor_a41_remote_cycle_campaign as campaign


def test_checkpoint_round_trip(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint.json"
    monkeypatch.setattr(campaign, "CHECKPOINT", checkpoint)
    current = {"name": "candidate", "parts": [{"type": "arm1"}]}
    mutations = [{"arm": 1, "delta": -1}]
    rounds = [{"round": 1, "sourceCycles": 1112, "candidates": []}]
    active = [{"shift": {"arm": 2, "delta": -1}, "valid": True, "cycles": 1109, "metrics": {"cycles": 1109}}]

    campaign.write_checkpoint(
        baseline_cycles=1112,
        current=current,
        current_cycles=1110,
        mutations=mutations,
        tested=17,
        valid=9,
        rounds=rounds,
        round_index=2,
        next_candidate_index=6,
        active_round_results=active,
    )

    loaded = campaign.load_checkpoint(1112)
    assert loaded is not None
    assert loaded["schemaVersion"] == 2
    assert loaded["current"] == current
    assert loaded["currentCycles"] == 1110
    assert loaded["testedCandidates"] == 17
    assert loaded["validCandidates"] == 9
    assert loaded["roundIndex"] == 2
    assert loaded["nextCandidateIndex"] == 6
    assert loaded["activeRoundResults"] == active


def test_checkpoint_rejects_wrong_baseline_or_endpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint.json"
    monkeypatch.setattr(campaign, "CHECKPOINT", checkpoint)
    checkpoint.write_text(
        json.dumps({
            "schemaVersion": 2,
            "validatorEndpoint": "/old-endpoint",
            "baselineCycles": 1112,
            "current": {"name": "candidate"},
        }),
        encoding="utf-8",
    )
    assert campaign.load_checkpoint(1112) is None

    checkpoint.write_text(
        json.dumps({
            "schemaVersion": 2,
            "validatorEndpoint": campaign.ANALYZE_ENDPOINT,
            "baselineCycles": 1111,
            "current": {"name": "candidate"},
        }),
        encoding="utf-8",
    )
    assert campaign.load_checkpoint(1112) is None


def test_best_from_partial_rebuilds_best_candidate(monkeypatch):
    current = {"seed": True}

    def fake_apply(model, shift):
        return {"seed": model["seed"], "shift": shift}

    monkeypatch.setattr(campaign, "apply_shift", fake_apply)
    results = [
        {"shift": {"id": "a"}, "valid": True, "cycles": 1110, "metrics": {"cycles": 1110}},
        {"shift": {"id": "b"}, "valid": False, "cycles": None, "metrics": None},
        {"shift": {"id": "c"}, "valid": True, "cycles": 1104, "metrics": {"cycles": 1104, "area": 41}},
    ]

    best = campaign.best_from_partial(current, 1112, results)
    assert best is not None
    cycles, shift, candidate, metrics = best
    assert cycles == 1104
    assert shift == {"id": "c"}
    assert candidate["shift"] == {"id": "c"}
    assert metrics["area"] == 41
