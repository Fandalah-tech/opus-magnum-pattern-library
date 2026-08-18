from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = ((process.stdout or "") + (process.stderr or "")).strip()
    match = _COLLISION_RE.search(text)
    if process.returncode == 0:
        progress = 1_000_000_000
    elif match:
        progress = int(match.group(1))
    elif "cycle limit" in text.lower():
        progress = 999_999_999
    else:
        progress = 0
    return {
        "exitCode": int(process.returncode),
        "output": text,
        "progressCycle": progress,
        "collisionCycle": int(match.group(1)) if match else None,
        "collisionLocation": [int(match.group(2)), int(match.group(3))] if match else None,
    }


def _score(record: dict[str, Any]) -> tuple[Any, ...]:
    profile = record.get("purificationProfile") or {}
    counts = profile.get("countsByElement") or {}
    oracle = record.get("omsim") or {}
    return (
        int(oracle.get("exitCode") == 0),
        int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1),
        int(counts.get("gold", 0)),
        int(counts.get("silver", 0)),
        int(counts.get("copper", 0)),
        int(profile.get("count") or 0),
        int(oracle.get("progressCycle") or 0),
        int(not bool(profile.get("terminatedWithError"))),
        int(profile.get("completedCycles") or 0),
    )


def select(
    omsim: Path,
    puzzle_path: Path,
    candidates: list[Path],
    selected_output: Path,
    *,
    max_cycles: int = 500,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    records: list[dict[str, Any]] = []
    for path in candidates:
        if not path.is_file():
            continue
        solution = parse_solution(path)
        profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
        oracle = _run_omsim(omsim, puzzle_path, path)
        records.append({
            "solutionPath": str(path),
            "purificationProfile": profile,
            "omsim": oracle,
        })
    records.sort(key=_score, reverse=True)
    best = records[0] if records else None
    if best:
        selected_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best["solutionPath"], selected_output)
        best = {**best, "selectedOutput": str(selected_output)}
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-current-frontier-requalification",
        "targetSolutionBytesUsed": 0,
        "request": {"maxCycles": max_cycles, "candidateCount": len(candidates)},
        "evaluatedCandidateCount": len(records),
        "best": best,
        "topCandidates": records[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Requalify generated heldout candidates against the current engine and pinned OMSim.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--candidate-glob", default="**/*.solution")
    parser.add_argument("--selected-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    args = parser.parse_args()

    candidates = sorted(args.candidate_root.glob(args.candidate_glob))
    report = select(
        args.omsim,
        args.puzzle,
        candidates,
        args.selected_output,
        max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "evaluatedCandidateCount": report["evaluatedCandidateCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
