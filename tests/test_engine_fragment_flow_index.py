from tools.build_engine_fragment_flow_index import select_engine_complete_records


def _audit(results):
    return {"results": results}


def test_source_holdout_excludes_puzzle_id_and_path_aliases():
    selected, source_filter = select_engine_complete_records(
        _audit([
            {
                "status": "engine-complete",
                "puzzleId": "OM2021_W1",
                "puzzlePath": "/puzzles/OM2021_W1.puzzle",
                "solutionPath": "target/a.solution",
            },
            {
                "status": "engine-complete",
                "puzzleId": "legacy-alias",
                "puzzlePath": r"C:\\puzzles\\om2021_w1.PUZZLE",
                "solutionPath": "target/b.solution",
            },
            {
                "status": "engine-complete",
                "puzzleId": "P017",
                "puzzlePath": "/puzzles/P017.puzzle",
                "solutionPath": "other/c.solution",
            },
            {
                "status": "engine-error",
                "puzzleId": "P017",
                "puzzlePath": "/puzzles/P017.puzzle",
                "solutionPath": "other/d.solution",
            },
        ]),
        exclude_puzzle_ids=["om2021_w1.puzzle"],
    )

    assert [record["solutionPath"] for record in selected] == ["other/c.solution"]
    assert source_filter == {
        "mode": "strict-source-holdout",
        "strictSourceFiltering": True,
        "requestedExcludedPuzzleIds": ["om2021_w1.puzzle"],
        "requestedExcludedSolutionPaths": [],
        "matchedExcludedPuzzleIds": ["om2021_w1"],
        "engineCompleteSolutionCountBeforeExclusion": 3,
        "excludedByPuzzleCount": 2,
        "excludedBySolutionCount": 0,
        "excludedEngineCompleteSolutionCount": 2,
        "eligibleEngineCompleteSolutionCount": 1,
    }


def test_source_holdout_can_exclude_an_exact_solution_without_double_counting():
    selected, source_filter = select_engine_complete_records(
        _audit([
            {
                "status": "engine-complete",
                "puzzleId": "target",
                "puzzlePath": "/puzzles/target.puzzle",
                "solutionPath": "Folder/A.solution",
            },
            {
                "status": "engine-complete",
                "puzzleId": "other",
                "puzzlePath": "/puzzles/other.puzzle",
                "solutionPath": "Folder/B.solution",
            },
        ]),
        exclude_puzzle_ids=["target"],
        exclude_solution_paths=[r".\Folder\A.solution", "folder/b.solution"],
    )

    assert selected == []
    assert source_filter["excludedByPuzzleCount"] == 1
    assert source_filter["excludedBySolutionCount"] == 1
    assert source_filter["excludedEngineCompleteSolutionCount"] == 2
