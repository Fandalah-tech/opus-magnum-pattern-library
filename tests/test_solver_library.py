from packages.opus_solver.library import build_solver_index, pareto_frontier


def record(sha, *, cycles, cost, area, instructions, mechanism="m1", structure="s1", puzzle="P001"):
    return {
        "status": "parsed-matched",
        "sha256": sha,
        "file": f"{sha}.solution",
        "puzzleFile": puzzle,
        "archivePuzzleName": "Puzzle One",
        "campaignPuzzleMatched": True,
        "metrics": {
            "cycles": cycles,
            "cost": cost,
            "area": area,
            "instructions": instructions,
        },
        "partTypes": ["arm1", "bonder"],
        "partCount": 3,
        "armCount": 1,
        "cycleSlots": cycles,
        "instructionCount": instructions,
        "architectureSignature": {"archetype": "balanced-cell" if mechanism == "m1" else "single-arm-sequential"},
        "canonicalStructuralHash": structure,
        "canonicalMechanismHash": mechanism,
    }


def test_pareto_frontier_removes_dominated_solution():
    a = record("a", cycles=10, cost=20, area=30, instructions=40)
    b = record("b", cycles=11, cost=20, area=31, instructions=40)
    c = record("c", cycles=9, cost=25, area=30, instructions=40)

    frontier = pareto_frontier([a, b, c])

    assert [item["sha256"] for item in frontier] == ["c", "a"]


def test_build_solver_index_groups_mechanisms_and_tracks_best_variants():
    analysis = {
        "schemaVersion": "0.2.0",
        "results": [
            record("a", cycles=10, cost=30, area=20, instructions=12, mechanism="m1", structure="s1"),
            record("b", cycles=9, cost=40, area=18, instructions=14, mechanism="m1", structure="s2"),
            record("c", cycles=15, cost=25, area=25, instructions=10, mechanism="m2", structure="s3"),
            {"status": "parse-error", "sha256": "bad"},
        ],
    }

    index = build_solver_index(analysis)

    assert index["summary"] == {
        "puzzleCount": 1,
        "solutionCount": 3,
        "mechanismCount": 2,
        "paretoRepresentativeCount": 3,
    }
    puzzle = index["puzzles"][0]
    assert puzzle["puzzleKey"] == "P001"
    assert puzzle["mechanismCount"] == 2

    first = next(item for item in puzzle["mechanisms"] if item["canonicalMechanismHash"] == "m1")
    assert first["solutionCount"] == 2
    assert first["structuralVariantCount"] == 2
    assert first["architectureArchetypes"] == ["balanced-cell"]
    assert first["bestByMetric"]["cycles"]["sha256"] == "b"
    assert first["bestByMetric"]["cost"]["sha256"] == "a"
    assert first["bestByMetric"]["area"]["sha256"] == "b"
