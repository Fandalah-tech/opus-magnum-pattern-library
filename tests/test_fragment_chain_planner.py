from packages.opus_solver import rank_fragment_chains


def _transition(source_role, source_hash, target_role, target_hash, relation, observations, puzzles=1, solutions=1):
    return {
        "sourceRole": source_role,
        "sourceMechanismHash": source_hash,
        "targetRole": target_role,
        "targetMechanismHash": target_hash,
        "relation": relation,
        "observationCount": observations,
        "sourcePuzzleCount": puzzles,
        "sourceSolutionCount": solutions,
    }


def test_rank_fragment_chains_prefers_broader_observed_path():
    flow = {"transitions": [
        _transition("feed", "f1", "conversion", "c1", "calcify", 8, 4, 6),
        _transition("conversion", "c1", "output", "o1", "delivered", 7, 4, 5),
        _transition("feed", "f2", "output", "o2", "delivered", 1, 1, 1),
    ]}

    ranked = rank_fragment_chains(flow, limit=10)

    assert ranked[0]["nodes"][0]["canonicalMechanismHash"] == "f1"
    assert ranked[0]["nodes"][-1]["canonicalMechanismHash"] == "o1"


def test_rank_fragment_chains_avoids_cycles():
    flow = {"transitions": [
        _transition("feed", "f", "conversion", "c", "calcify", 3),
        _transition("conversion", "c", "feed", "f", "loop", 3),
        _transition("conversion", "c", "output", "o", "delivered", 3),
    ]}

    ranked = rank_fragment_chains(flow, max_depth=6)

    assert len(ranked) == 1
    assert [node["canonicalMechanismHash"] for node in ranked[0]["nodes"]] == ["f", "c", "o"]


def test_rank_fragment_chains_respects_min_observations():
    flow = {"transitions": [
        _transition("feed", "weak", "output", "o1", "delivered", 1),
        _transition("feed", "strong", "output", "o2", "delivered", 4),
    ]}

    ranked = rank_fragment_chains(flow, min_observations=2)

    assert len(ranked) == 1
    assert ranked[0]["nodes"][0]["canonicalMechanismHash"] == "strong"
