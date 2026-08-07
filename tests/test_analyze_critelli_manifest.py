from tools.analyze_critelli_manifest import build, dominates, pareto_front


def sol(sid, c, cost, area, ins, player=None):
    return {
        "id": sid,
        "puzzleId": "p1",
        "metrics": {"cycles": c, "cost": cost, "area": area, "instructions": ins},
        "submitter": player,
    }


def test_dominance_and_front():
    a = sol("a", 10, 10, 10, 10)
    b = sol("b", 11, 10, 10, 10)
    c = sol("c", 9, 20, 10, 10)
    assert dominates(a, b)
    assert not dominates(a, c)
    assert {x["id"] for x in pareto_front([a, b, c])} == {"a", "c"}


def test_build_records_and_players():
    manifest = {
        "id": "critelli-public-events",
        "puzzles": [{"id": "p1", "name": "Puzzle One", "eventTitle": "Event"}],
        "solutions": [
            sol("a", 10, 10, 10, 10, "Alice"),
            sol("b", 11, 10, 10, 10, "Bob"),
            sol("c", 9, 20, 10, 10, "Alice"),
        ],
    }
    out = build(manifest)
    assert out["summary"]["puzzleCount"] == 1
    assert out["summary"]["paretoSolutionCount"] == 2
    p = out["puzzles"][0]
    assert p["records"]["cycles"]["value"] == 9
    assert set(p["paretoSolutionIds"]) == {"a", "c"}
    alice = next(x for x in out["players"] if x["player"] == "Alice")
    assert alice["solutionCount"] == 2
    assert alice["paretoSolutionCount"] == 2
