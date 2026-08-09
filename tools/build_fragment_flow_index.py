from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import (
    build_fragment_flow_graph,
    canonical_convergence_key,
    extract_convergence_motifs,
)
from packages.opus_parser import parse_puzzle, parse_solution


def _puzzle_lookup(root: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    if not root.exists():
        return lookup
    for path in root.rglob("*.puzzle"):
        lookup.setdefault(path.name.lower(), path)
        lookup.setdefault(path.stem.lower(), path)
    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(description="Build replay-backed canonical flow transitions and convergence motifs between functional fragments.")
    parser.add_argument("--archive-root", type=Path, default=Path(".datasets/solution-archive"))
    parser.add_argument("--puzzle-root", type=Path, default=Path(".datasets/archive-campaign-reference"))
    parser.add_argument("--output", type=Path, default=Path("database/fragment-flow-index.json"))
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()

    archive_index = json.loads((args.archive_root / "index.json").read_text(encoding="utf-8"))
    puzzle_lookup = _puzzle_lookup(args.puzzle_root)
    puzzle_cache: dict[Path, dict[str, Any]] = {}
    groups: defaultdict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    convergence_groups: defaultdict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    errors = []
    replay_solutions = 0
    raw_edges = 0
    raw_convergences = 0
    relation_counts: Counter[str] = Counter()

    for item in archive_index.get("solutions", []):
        path = args.archive_root / str(item["file"])
        try:
            solution = parse_solution(path)
            puzzle_key = str(solution.get("puzzleFile") or item.get("puzzleName") or "<unknown>")
            puzzle_path = puzzle_lookup.get(Path(puzzle_key).name.lower()) or puzzle_lookup.get(Path(puzzle_key).stem.lower())
            if puzzle_path is None:
                continue
            puzzle = puzzle_cache.setdefault(puzzle_path, parse_puzzle(puzzle_path))
            graph = build_fragment_flow_graph(puzzle, solution)
            replay_solutions += 1
            solution_sha = item.get("sha256") or solution.get("source", {}).get("sha256")

            for edge in graph.get("edges", []):
                raw_edges += 1
                relation = str(edge.get("relation") or "unknown")
                relation_counts[relation] += int(edge.get("observationCount") or 0)
                key = (
                    str(edge.get("sourceRole") or ""),
                    str(edge.get("sourceMechanismHash") or ""),
                    str(edge.get("targetRole") or ""),
                    str(edge.get("targetMechanismHash") or ""),
                    relation,
                )
                groups[key].append({
                    "puzzleKey": puzzle_key,
                    "solutionSha256": solution_sha,
                    "solutionFile": item.get("file"),
                    **edge,
                })

            for motif in extract_convergence_motifs(graph):
                raw_convergences += 1
                convergence_groups[canonical_convergence_key(motif)].append({
                    "puzzleKey": puzzle_key,
                    "solutionSha256": solution_sha,
                    "solutionFile": item.get("file"),
                    **motif,
                })
        except Exception as exc:
            errors.append({"file": item.get("file"), "errorType": type(exc).__name__, "message": str(exc)})

    transitions = []
    for key, records in sorted(groups.items()):
        source_role, source_hash, target_role, target_hash, relation = key
        puzzles = sorted({str(record["puzzleKey"]) for record in records})
        solutions = sorted({str(record["solutionSha256"]) for record in records if record.get("solutionSha256")})
        observation_count = sum(int(record.get("observationCount") or 0) for record in records)
        transitions.append({
            "sourceRole": source_role,
            "sourceMechanismHash": source_hash,
            "targetRole": target_role,
            "targetMechanismHash": target_hash,
            "relation": relation,
            "observationCount": observation_count,
            "sourcePuzzleCount": len(puzzles),
            "sourceSolutionCount": len(solutions),
            "sourcePuzzles": puzzles,
            "samples": [
                {
                    "puzzleKey": record["puzzleKey"],
                    "solutionSha256": record.get("solutionSha256"),
                    "solutionFile": record.get("solutionFile"),
                    "firstCycle": record.get("firstCycle"),
                    "lastCycle": record.get("lastCycle"),
                    "observationCount": record.get("observationCount"),
                }
                for record in records[:max(0, args.sample_limit)]
            ],
        })

    convergence_motifs = []
    for key, records in sorted(convergence_groups.items(), key=lambda item: str(item[0])):
        input_key, target_role, target_hash = key
        puzzles = sorted({str(record["puzzleKey"]) for record in records})
        solutions = sorted({str(record["solutionSha256"]) for record in records if record.get("solutionSha256")})
        canonical_inputs = [
            {
                "sourceRole": source_role,
                "sourceMechanismHash": source_hash,
                "relations": list(relations),
            }
            for source_role, source_hash, relations in input_key
        ]
        convergence_motifs.append({
            "targetRole": target_role,
            "targetMechanismHash": target_hash,
            "inputCount": len(canonical_inputs),
            "inputs": canonical_inputs,
            "observationCount": len(records),
            "sourcePuzzleCount": len(puzzles),
            "sourceSolutionCount": len(solutions),
            "sourcePuzzles": puzzles,
            "samples": [
                {
                    "puzzleKey": record["puzzleKey"],
                    "solutionSha256": record.get("solutionSha256"),
                    "solutionFile": record.get("solutionFile"),
                    "targetAnchorPartId": record.get("targetAnchorPartId"),
                    "inputs": record.get("inputs", []),
                    "outputs": record.get("outputs", []),
                }
                for record in records[:max(0, args.sample_limit)]
            ],
        })

    index = {
        "schemaVersion": "0.2.0",
        "summary": {
            "replaySolutionCount": replay_solutions,
            "rawFlowEdgeCount": raw_edges,
            "canonicalTransitionCount": len(transitions),
            "flowObservationCount": sum(item["observationCount"] for item in transitions),
            "rawConvergenceMotifCount": raw_convergences,
            "canonicalConvergenceMotifCount": len(convergence_motifs),
            "relationCounts": dict(sorted(relation_counts.items())),
            "errorCount": len(errors),
        },
        "transitions": transitions,
        "convergenceMotifs": convergence_motifs,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
