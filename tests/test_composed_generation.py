from packages.opus_solver.generation import generate_composed_candidates


def test_unsupported_puzzle_returns_clean_generation_report():
    puzzle = {"name": "Unsupported", "products": [], "reagents": [], "availableParts": {"glyphs": []}}
    result = generate_composed_candidates(puzzle, {"transitions": [], "convergenceMotifs": []}, {"fragments": []}, validate_engine=False)
    assert result["summary"]["supported"] is False
    assert result["summary"]["assemblyCandidateCount"] == 0
    assert result["candidates"] == []


def test_supported_plan_with_no_historical_assembly_returns_empty_candidates():
    puzzle = {
        "name": "Pair",
        "source": {"name": "P.puzzle"},
        "availableParts": {"glyphs": ["bonder", "calcification"]},
        "reagents": [
            {"atoms": [{"id": "a0", "element": "air", "position": [0, 0]}], "bonds": []},
            {"atoms": [{"id": "a0", "element": "fire", "position": [0, 0]}], "bonds": []},
        ],
        "products": [
            {
                "atoms": [
                    {"id": "p0", "element": "air", "position": [0, 0]},
                    {"id": "p1", "element": "salt", "position": [1, 0]},
                ],
                "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
            }
        ],
    }
    result = generate_composed_candidates(puzzle, {"transitions": [], "convergenceMotifs": []}, {"fragments": []}, validate_engine=False)
    assert result["summary"]["supported"] is True
    assert result["summary"]["assemblyCandidateCount"] == 0
    assert result["summary"]["serializableCount"] == 0
