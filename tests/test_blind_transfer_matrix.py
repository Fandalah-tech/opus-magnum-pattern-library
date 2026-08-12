from pathlib import Path
from unittest.mock import patch

from packages.opus_parser import ParseError
from packages.opus_solver import BlindTransferContractError
from tools.validate_blind_transfer_matrix import validate_blind_transfer_matrix


def _puzzle(path: Path) -> dict:
    return {
        "source": {"name": path.name},
        "name": path.stem.upper(),
        "production": False,
    }


def test_matrix_scans_only_puzzles_and_aggregates_blind_results(tmp_path: Path) -> None:
    puzzle_root = tmp_path / "puzzles"
    puzzle_root.mkdir()
    donor_path = puzzle_root / "donor.puzzle"
    solved_path = puzzle_root / "solved.puzzle"
    rejected_path = puzzle_root / "rejected.puzzle"
    excluded_path = puzzle_root / "excluded.puzzle"
    invalid_path = puzzle_root / "invalid.puzzle"
    for path in (donor_path, solved_path, rejected_path, excluded_path, invalid_path):
        path.write_bytes(b"fixture")
    donor_solution = tmp_path / "donor.solution"
    donor_solution.write_bytes(b"fixture")

    def fake_transfer(target_path, *_args, **_kwargs):
        if target_path == rejected_path:
            raise BlindTransferContractError("chemistry mismatch")
        return {
            "status": "ready",
            "summary": {
                "candidateCount": 3,
                "validCandidateCount": 2,
                "targetSolutionCountRead": 0,
            },
            "winner": {
                "candidateId": "direct-transfer-002",
                "targetMapping": {"reagentIndex": 1, "productIndex": 0},
                "sourcePartIds": ["input", "output", "arm"],
                "oracleValidation": {
                    "metrics": {"cost": 40, "cycles": 23, "area": 3, "instructions": 4},
                    "rate": 4,
                },
            },
        }

    def fake_parse(path):
        path = Path(path)
        if path == invalid_path:
            raise ParseError("unsupported bond")
        return _puzzle(path)

    with patch(
        "tools.validate_blind_transfer_matrix.parse_puzzle",
        side_effect=fake_parse,
    ), patch(
        "tools.validate_blind_transfer_matrix.transfer_solution_blind",
        side_effect=fake_transfer,
    ):
        report = validate_blind_transfer_matrix(
            puzzle_root,
            donor_path,
            donor_solution,
            tmp_path / "report",
            omsim=tmp_path / "omsim",
            excluded_target_ids={"excluded"},
        )

    assert report["status"] == "ready"
    assert report["summary"] == {
        "puzzleFileCount": 5,
        "excludedTargetCount": 2,
        "parseFailureCount": 1,
        "incompatibleTargetCount": 1,
        "compatibleTargetCount": 1,
        "solvedTargetCount": 1,
        "unsolvedTargetCount": 0,
        "candidateCount": 3,
        "validCandidateCount": 2,
        "targetSolutionCountRead": 0,
    }
    assert report["targets"][0]["targetPuzzleId"] == "solved"
    assert report["targets"][0]["targetMapping"]["reagentIndex"] == 1
    assert Path(report["textReportPath"]).read_text(encoding="utf-8").startswith(
        "BLIND TRANSFER REGRESSION MATRIX"
    )
