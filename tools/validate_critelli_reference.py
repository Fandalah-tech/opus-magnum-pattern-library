from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from packages.opus_analysis import canonical_solution_hash
from packages.opus_parser import parse_puzzle, parse_solution
from packages.opus_solver import validate_generated_solution


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_reference_bank(
    puzzle_path: Path,
    solutions_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        str(item["file"]): item
        for item in manifest.get("novelFixtures", [])
        if item.get("file")
    }
    results: list[dict[str, Any]] = []

    for relative, reference in sorted(expected.items()):
        path = manifest_path.parent / relative
        record: dict[str, Any] = {
            "file": relative,
            "exists": path.exists(),
            "expectedSha256": reference.get("sha256"),
            "expectedCanonicalMechanismHash": reference.get("canonicalMechanismHash"),
        }
        if not path.exists():
            record.update({"complete": False, "error": "missing-fixture"})
            results.append(record)
            continue
        try:
            observed_sha = sha256(path)
            solution = parse_solution(path)
            observed_mechanism = canonical_solution_hash(solution, normalize_time=True)
            validation = validate_generated_solution(puzzle, solution)
            record.update({
                "observedSha256": observed_sha,
                "sha256Matches": observed_sha == reference.get("sha256"),
                "observedCanonicalMechanismHash": observed_mechanism,
                "canonicalMechanismMatches": observed_mechanism == reference.get("canonicalMechanismHash"),
                "complete": bool(validation.get("complete")),
                "validation": validation,
            })
        except Exception as exc:
            record.update({
                "complete": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
        results.append(record)

    unexpected = sorted(
        path.relative_to(manifest_path.parent).as_posix()
        for path in solutions_dir.glob("*.solution")
        if path.relative_to(manifest_path.parent).as_posix() not in expected
    )
    passed = [
        item for item in results
        if item.get("exists")
        and item.get("sha256Matches")
        and item.get("canonicalMechanismMatches")
        and item.get("complete")
    ]
    summary = {
        "expectedFixtureCount": len(expected),
        "validatedFixtureCount": len(results),
        "passedFixtureCount": len(passed),
        "failedFixtureCount": len(results) - len(passed),
        "unexpectedFixtureCount": len(unexpected),
        "allPassed": len(results) == len(expected) == len(passed) and not unexpected,
    }
    return {
        "schemaVersion": "0.1.0",
        "eventId": manifest.get("eventId"),
        "puzzle": str(puzzle.get("name") or puzzle_path.stem),
        "manifest": str(manifest_path),
        "summary": summary,
        "unexpectedFixtures": unexpected,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate persisted Critelli-generated regression solutions against a freshly fetched puzzle.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--solutions-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = validate_reference_bank(args.puzzle, args.solutions_dir, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if args.strict and not report["summary"]["allPassed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
