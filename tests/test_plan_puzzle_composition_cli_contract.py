from packages.opus_solver.chemistry_composition import plan_puzzle_fragment_chains


def test_unsupported_puzzle_returns_explained_empty_plan():
    puzzle = {
        "products": [],
        "reagents": [],
        "availableParts": {"glyphs": []},
    }
    result = plan_puzzle_fragment_chains(puzzle, {"transitions": []})
    assert result["summary"]["supported"] is False
    assert result["summary"]["candidateCount"] == 0
    assert result["requirements"]["reason"]
    assert result["chains"] == []
