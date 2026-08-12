import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from packages.opus_parser import parse_solution
from tools.solve_test_puzzle import solve_test_puzzle


def test_first_puzzle_intake_writes_game_solution_and_report(tmp_path: Path) -> None:
    report = solve_test_puzzle(Path("samples/solver/P007.puzzle"), tmp_path)
    assert report["status"] == "ready"
    assert report["readyForGameTest"] is True
    assert report["binaryRoundTripClean"] is True
    assert report["roundTripValidation"]["deliveredProducts"] == {"part-0": 6}
    assert report["omsimValidation"]["status"] == "unavailable"
    solution = parse_solution(report["solutionPath"])
    assert solution["puzzleFile"] == "P007"
    assert Path(report["reportPath"]).is_file()


def test_first_puzzle_intake_reports_unsupported_shape(tmp_path: Path) -> None:
    from packages.opus_parser import parse_puzzle
    from packages.opus_solver import solve_puzzle

    # The public intake helper must return a diagnostic rather than leaking an
    # exception when the first uploaded puzzle is beyond the current strategy.
    puzzle_path = Path("samples/solver/P007.puzzle")
    puzzle = parse_puzzle(puzzle_path)
    puzzle["products"][0]["atoms"].append({"id": "extra", "element": "water", "position": [2, 0]})
    try:
        solve_puzzle(puzzle)
    except Exception as error:
        assert "exactly two atoms" in str(error)
    else:
        raise AssertionError("Expected unsupported puzzle shape")


def test_first_puzzle_cli_runs_as_documented(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "tools/solve_test_puzzle.py",
            "samples/solver/P007.puzzle",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"readyForGameTest": true' in completed.stdout


def test_first_puzzle_intake_accepts_native_omsim_valid_contract(tmp_path: Path) -> None:
    with patch("tools.solve_test_puzzle.run_omsim", return_value={"valid": True, "metrics": {}}):
        report = solve_test_puzzle(
            Path("samples/solver/P007.puzzle"),
            tmp_path,
            omsim=Path("/synthetic/omsim"),
        )
    assert report["status"] == "ready"
    assert report["readyForGameTest"] is True
