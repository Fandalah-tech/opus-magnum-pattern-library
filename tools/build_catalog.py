from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MANIFEST = Path("fixtures/reference/campaign-p007-p015.manifest.json")
DEFAULT_OUTPUT = Path("database/catalog.json")
SOURCE_DATASET = "campaign-p007-p015-user-reference"


def stable_id(prefix: str, sha256: str) -> str:
    value = str(sha256).strip().lower()
    if len(value) < 16:
        raise ValueError(f"Invalid sha256 for {prefix}: {sha256!r}")
    return f"{prefix}-{value[:16]}"


def build(manifest: dict) -> dict:
    puzzles: list[dict] = []
    solutions: list[dict] = []
    puzzle_ids: set[str] = set()
    solution_ids: set[str] = set()

    redistribution = manifest.get("redistribution", "metadata-only")
    dataset_id = manifest.get("id", SOURCE_DATASET)

    for pair in manifest.get("pairs", []):
        puzzle = pair["puzzle"]
        solution = pair["solution"]
        puzzle_id = stable_id("puz", puzzle["sha256"])
        solution_id = stable_id("sol", solution["sha256"])

        if puzzle_id not in puzzle_ids:
            puzzles.append({
                "id": puzzle_id,
                "sha256": puzzle["sha256"],
                "name": puzzle.get("name") or puzzle.get("file") or puzzle_id,
                "file": puzzle.get("file"),
                "version": puzzle.get("version"),
                "size": puzzle.get("size"),
                "sourceDataset": dataset_id,
                "redistribution": redistribution,
                "tags": ["campaign", "reference-fixture"],
            })
            puzzle_ids.add(puzzle_id)

        if solution_id in solution_ids:
            continue
        checks = pair.get("parserChecks", {})
        solutions.append({
            "id": solution_id,
            "sha256": solution["sha256"],
            "puzzleId": puzzle_id,
            "file": solution.get("file"),
            "version": solution.get("version"),
            "size": solution.get("size"),
            "metrics": {
                "cycles": solution.get("metrics", {}).get("cycles"),
                "cost": solution.get("metrics", {}).get("cost"),
                "area": solution.get("metrics", {}).get("area"),
                "instructions": solution.get("metrics", {}).get("instructions"),
            },
            "validation": {
                "parserClean": checks.get("puzzleTrailingBytes") == 0 and checks.get("solutionTrailingBytes") == 0,
                "omsim": "validated" if solution.get("metrics") else None,
                "replayEquivalent": True if puzzle.get("file") in {"P012.puzzle", "P013.puzzle", "P015.puzzle"} else None,
            },
            "sourceDataset": dataset_id,
            "redistribution": redistribution,
            "tags": ["campaign", "reference-solution"],
        })
        solution_ids.add(solution_id)

    puzzles.sort(key=lambda item: (item["name"], item["id"]))
    solutions.sort(key=lambda item: (item["puzzleId"], item["metrics"].get("cycles") or 10**12, item["id"]))
    validated = sum(1 for item in solutions if item["validation"].get("omsim") == "validated")
    return {
        "schemaVersion": "0.1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": [dataset_id],
        "summary": {
            "puzzleCount": len(puzzles),
            "solutionCount": len(solutions),
            "validatedSolutionCount": validated,
        },
        "puzzles": puzzles,
        "solutions": solutions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the canonical Opus Magnum puzzle/solution catalog.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    catalog = build(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(catalog["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
