from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_analysis import canonical_solution_hash, solution_architecture_signature
from packages.opus_parser import parse_solution


def assess_composed_novelty(
    analysis_path: Path,
    generated_dir: Path,
) -> dict[str, Any]:
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    originals = [item for item in analysis.get("results", []) if item.get("status", "").startswith("parsed-")]
    structural_to_sources: dict[str, list[str]] = {}
    mechanism_to_sources: dict[str, list[str]] = {}
    for item in originals:
        source = str(item.get("file") or "")
        structural_to_sources.setdefault(str(item.get("canonicalStructuralHash") or ""), []).append(source)
        mechanism_to_sources.setdefault(str(item.get("canonicalMechanismHash") or ""), []).append(source)

    results: list[dict[str, Any]] = []
    for path in sorted(generated_dir.glob("*.solution")):
        solution = parse_solution(path)
        structural_hash = canonical_solution_hash(solution, normalize_time=False)
        mechanism_hash = canonical_solution_hash(solution, normalize_time=True)
        structural_matches = structural_to_sources.get(structural_hash, [])
        mechanism_matches = mechanism_to_sources.get(mechanism_hash, [])
        results.append({
            "file": path.name,
            "canonicalStructuralHash": structural_hash,
            "canonicalMechanismHash": mechanism_hash,
            "exactStructuralMatches": structural_matches,
            "exactMechanismMatches": mechanism_matches,
            "novelStructure": not structural_matches,
            "novelMechanism": not mechanism_matches,
            "architectureSignature": solution_architecture_signature(solution),
        })

    return {
        "schemaVersion": "0.1.0",
        "sourceAnalysis": str(analysis_path),
        "generatedDirectory": str(generated_dir),
        "summary": {
            "originalSolutionCount": len(originals),
            "generatedSolutionCount": len(results),
            "novelStructureCount": sum(bool(item["novelStructure"]) for item in results),
            "novelMechanismCount": sum(bool(item["novelMechanism"]) for item in results),
            "exactStructureReuseCount": sum(not bool(item["novelStructure"]) for item in results),
            "exactMechanismReuseCount": sum(not bool(item["novelMechanism"]) for item in results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare composed solutions with the source corpus using canonical hashes.")
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = assess_composed_novelty(args.analysis, args.generated_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
