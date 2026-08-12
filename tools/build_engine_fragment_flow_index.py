from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_analysis import (
    build_engine_fragment_flow_graph,
    bounded_audit_workers,
    canonical_convergence_key,
    extract_convergence_motifs,
)
from packages.opus_parser import parse_puzzle, parse_solution


def _build_graph(item: tuple[str, str, str]) -> dict[str, Any]:
    puzzle_path, solution_path, relative_path = item
    try:
        puzzle = parse_puzzle(puzzle_path)
        solution = parse_solution(solution_path)
        graph = build_engine_fragment_flow_graph(puzzle, solution)
        return {"solutionPath": relative_path, "graph": graph}
    except Exception as exc:
        return {
            "solutionPath": relative_path,
            "errorType": type(exc).__name__,
            "message": str(exc),
        }


def _json_key(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


def _invariant_timing(timing: dict[str, Any] | None) -> dict[str, Any] | None:
    if not timing:
        return None
    return {
        "frame": "source-fragment-program-start",
        "programStartDelta": timing.get("programStartDelta"),
        "eventFirstFromSourceStart": timing.get("eventFirstFromSourceStart"),
        "eventFirstFromTargetStart": timing.get("eventFirstFromTargetStart"),
    }


def _variant_summary(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    weighted: Counter[str] = Counter()
    payloads: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = record.get(field)
        if field == "relativeTiming":
            payload = _invariant_timing(payload)
        if not payload:
            continue
        key = _json_key(payload)
        payloads[key] = payload
        weighted[key] += max(1, int(record.get("observationCount") or 0))
    variants = [
        {field: payloads[key], "observationCount": count}
        for key, count in sorted(weighted.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "preferred": variants[0][field] if variants else None,
        "variantCount": len(variants),
        "variants": variants,
    }


def build_engine_fragment_flow_index(
    audit_report: dict[str, Any],
    *,
    workers: int = 10,
    sample_limit: int = 5,
) -> dict[str, Any]:
    solution_root = Path(str(audit_report["solutionRoot"]))
    eligible = [
        record
        for record in audit_report.get("results", [])
        if record.get("status") == "engine-complete"
    ]
    items = [
        (
            str(record["puzzlePath"]),
            str(solution_root / str(record["solutionPath"])),
            str(record["solutionPath"]),
        )
        for record in eligible
        if record.get("puzzlePath")
    ]
    worker_count = bounded_audit_workers(workers)
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        graph_results = list(executor.map(_build_graph, items))

    groups: defaultdict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    fragment_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    convergence_groups: defaultdict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    validation_drift: list[dict[str, Any]] = []
    relation_counts: Counter[str] = Counter()
    replay_solution_count = 0
    raw_edge_count = 0
    raw_fragment_count = 0
    raw_convergence_count = 0
    for result in graph_results:
        if "graph" not in result:
            errors.append(result)
            continue
        graph = result["graph"]
        validation = graph.get("engineValidation", {})
        if not validation.get("complete"):
            validation_drift.append({
                "solutionPath": result["solutionPath"],
                "engineValidation": validation,
            })
            continue
        replay_solution_count += 1
        puzzle_id = str(graph.get("source", {}).get("puzzleFile") or "<unknown>")
        solution_sha = graph.get("source", {}).get("solutionSha256")
        for node in graph.get("nodes", []):
            raw_fragment_count += 1
            fragment_groups[(
                str(node.get("role") or ""),
                str(node.get("canonicalMechanismHash") or ""),
            )].append({
                **node,
                "puzzleId": puzzle_id,
                "solutionPath": result["solutionPath"],
                "solutionSha256": solution_sha,
            })
        for edge in graph.get("edges", []):
            raw_edge_count += 1
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
                **edge,
                "puzzleId": puzzle_id,
                "solutionPath": result["solutionPath"],
                "solutionSha256": solution_sha,
            })
        for motif in extract_convergence_motifs(graph):
            raw_convergence_count += 1
            convergence_groups[canonical_convergence_key(motif)].append({
                **motif,
                "puzzleId": puzzle_id,
                "solutionPath": result["solutionPath"],
                "solutionSha256": solution_sha,
            })

    transitions = []
    for key, records in sorted(groups.items()):
        source_role, source_hash, target_role, target_hash, relation = key
        puzzles = sorted({record["puzzleId"] for record in records})
        solutions = sorted({record["solutionPath"] for record in records})
        observation_count = sum(int(record.get("observationCount") or 0) for record in records)
        transitions.append({
            "sourceRole": source_role,
            "sourceMechanismHash": source_hash,
            "targetRole": target_role,
            "targetMechanismHash": target_hash,
            "relation": relation,
            "relativeTransforms": _variant_summary(records, "relativeTransform"),
            "relativeTimings": _variant_summary(records, "relativeTiming"),
            "observationCount": observation_count,
            "sourcePuzzleCount": len(puzzles),
            "sourceSolutionCount": len(solutions),
            "engineValidatedSolutionCount": len(solutions),
            "engineValidationRate": 1.0,
            "sourcePuzzles": puzzles,
            "sourceSolutions": solutions,
            "evidenceSource": "opus-engine-complete",
            "solutionVariants": [
                {
                    "puzzleId": record["puzzleId"],
                    "solutionPath": record["solutionPath"],
                    "sourceAnchorPartId": record.get("sourceAnchorPartId"),
                    "targetAnchorPartId": record.get("targetAnchorPartId"),
                    "relativeTransform": record.get("relativeTransform"),
                    "relativeTiming": _invariant_timing(record.get("relativeTiming")),
                    "observationCount": record.get("observationCount"),
                }
                for record in records
            ],
            "samples": [
                {
                    "puzzleId": record["puzzleId"],
                    "solutionPath": record["solutionPath"],
                    "solutionSha256": record.get("solutionSha256"),
                    "firstCycle": record.get("firstCycle"),
                    "lastCycle": record.get("lastCycle"),
                    "observationCount": record.get("observationCount"),
                    "relativeTransform": record.get("relativeTransform"),
                    "relativeTiming": record.get("relativeTiming"),
                }
                for record in records[:max(0, int(sample_limit))]
            ],
        })

    fragments = []
    for (role, mechanism_hash), records in sorted(fragment_groups.items()):
        representative = min(
            records,
            key=lambda item: (
                0 if item.get("evidenceLevel") == "engine-confirmed" else 1,
                int((item.get("summary") or {}).get("partCount") or 10**9),
                int((item.get("summary") or {}).get("instructionCount") or 10**9),
                str(item.get("solutionPath") or ""),
            ),
        )
        puzzles = sorted({str(record["puzzleId"]) for record in records})
        solutions = sorted({str(record["solutionPath"]) for record in records})
        structural_hashes = sorted({
            str(record.get("canonicalStructuralHash") or "")
            for record in records
            if record.get("canonicalStructuralHash")
        })
        part_types = sorted({
            str(part.get("type") or "")
            for record in records
            for part in (record.get("representativeGeometry") or {}).get("parts", [])
            if part.get("type")
        })
        fragments.append({
            "role": role,
            "canonicalMechanismHash": mechanism_hash,
            "occurrenceCount": len(records),
            "sourcePuzzleCount": len(puzzles),
            "sourceSolutionCount": len(solutions),
            "sourcePuzzles": puzzles,
            "structuralVariantCount": len(structural_hashes),
            "canonicalStructuralHashes": structural_hashes,
            "partTypes": part_types,
            "representativeGeometry": representative.get("representativeGeometry"),
            "representativeSource": {
                "puzzleId": representative.get("puzzleId"),
                "solutionPath": representative.get("solutionPath"),
                "solutionSha256": representative.get("solutionSha256"),
                "evidenceLevel": representative.get("evidenceLevel"),
            },
            "evidence": {
                "source": "opus-engine-complete",
                "engineValidatedSolutionCount": len(solutions),
                "engineValidationRate": 1.0,
            },
            "samples": [
                {
                    "puzzleId": record.get("puzzleId"),
                    "solutionPath": record.get("solutionPath"),
                    "solutionSha256": record.get("solutionSha256"),
                    "anchorPartType": record.get("anchorPartType"),
                    "summary": record.get("summary", {}),
                    "evidenceLevel": record.get("evidenceLevel"),
                }
                for record in records[:max(0, int(sample_limit))]
            ],
        })

    convergence_motifs = []
    for key, records in sorted(convergence_groups.items(), key=lambda item: str(item[0])):
        input_key, target_role, target_hash = key
        puzzles = sorted({str(record["puzzleId"]) for record in records})
        solutions = sorted({str(record["solutionPath"]) for record in records})
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
            "engineValidatedSolutionCount": len(solutions),
            "engineValidationRate": 1.0,
            "sourcePuzzles": puzzles,
            "sourceSolutions": solutions,
            "evidenceSource": "opus-engine-complete",
            "solutionSamples": [
                {
                    "puzzleId": record.get("puzzleId"),
                    "solutionPath": record.get("solutionPath"),
                    "solutionSha256": record.get("solutionSha256"),
                    "targetAnchorPartId": record.get("targetAnchorPartId"),
                    "inputs": record.get("inputs", []),
                    "outputs": record.get("outputs", []),
                }
                for record in records
            ],
            "samples": [
                {
                    "puzzleId": record.get("puzzleId"),
                    "solutionPath": record.get("solutionPath"),
                    "solutionSha256": record.get("solutionSha256"),
                    "targetAnchorPartId": record.get("targetAnchorPartId"),
                    "inputs": record.get("inputs", []),
                    "outputs": record.get("outputs", []),
                }
                for record in records[:max(0, int(sample_limit))]
            ],
        })

    return {
        "schemaVersion": "0.6.0",
        "analysis": "engine-validated-fragment-flow-index",
        "sourceAuditSchemaVersion": audit_report.get("schemaVersion"),
        "summary": {
            "auditedSolutionCount": int(audit_report.get("summary", {}).get("solutionCount") or 0),
            "eligibleEngineCompleteSolutionCount": len(eligible),
            "replayValidatedSolutionCount": replay_solution_count,
            "validationDriftCount": len(validation_drift),
            "rawFlowEdgeCount": raw_edge_count,
            "canonicalTransitionCount": len(transitions),
            "flowObservationCount": sum(item["observationCount"] for item in transitions),
            "rawFragmentCount": raw_fragment_count,
            "canonicalFragmentCount": len(fragments),
            "rawConvergenceMotifCount": raw_convergence_count,
            "canonicalConvergenceMotifCount": len(convergence_motifs),
            "triplexTransitionCount": sum(str(item["relation"]).startswith("triplex-bond-created:") for item in transitions),
            "triplexObservationCount": sum(
                int(item["observationCount"])
                for item in transitions
                if str(item["relation"]).startswith("triplex-bond-created:")
            ),
            "relationCounts": dict(sorted(relation_counts.items())),
            "workerCount": worker_count,
            "errorCount": len(errors),
        },
        "transitions": transitions,
        "fragments": fragments,
        "convergenceMotifs": convergence_motifs,
        "validationDrift": validation_drift,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Learn fragment transitions only from engine-complete corpus solutions.")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    index = build_engine_fragment_flow_index(
        audit,
        workers=args.workers,
        sample_limit=args.sample_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["summary"], sort_keys=True))
    return 1 if index["summary"]["errorCount"] or index["summary"]["validationDriftCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
