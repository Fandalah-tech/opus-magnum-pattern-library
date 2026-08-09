from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

METRIC_NAMES = ("cycles", "cost", "area", "instructions")


def _metric_value(record: dict[str, Any], metric: str) -> int | None:
    value = record.get("metrics", {}).get(metric)
    return value if isinstance(value, int) else None


def _solution_ref(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "sha256": record.get("sha256"),
        "file": record.get("file"),
        "canonicalStructuralHash": record.get("canonicalStructuralHash"),
        "metrics": {name: _metric_value(record, name) for name in METRIC_NAMES},
    }


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    comparable = []
    strictly_better = False
    for metric in METRIC_NAMES:
        a = _metric_value(left, metric)
        b = _metric_value(right, metric)
        if a is None or b is None:
            continue
        comparable.append(metric)
        if a > b:
            return False
        if a < b:
            strictly_better = True
    return bool(comparable) and strictly_better


def pareto_frontier(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(records)
    frontier = []
    for index, candidate in enumerate(items):
        if any(index != other_index and _dominates(other, candidate) for other_index, other in enumerate(items)):
            continue
        frontier.append(candidate)
    return sorted(frontier, key=lambda item: tuple(_metric_value(item, metric) if _metric_value(item, metric) is not None else 10**12 for metric in METRIC_NAMES))


def _range(records: list[dict[str, Any]], field: str) -> dict[str, int | None]:
    values = [record.get(field) for record in records if isinstance(record.get(field), int)]
    return {"min": min(values) if values else None, "max": max(values) if values else None}


def build_solver_index(analysis: dict[str, Any]) -> dict[str, Any]:
    parsed = [
        record
        for record in analysis.get("results", [])
        if str(record.get("status", "")).startswith("parsed-") and record.get("canonicalMechanismHash")
    ]

    by_puzzle: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in parsed:
        puzzle_key = str(record.get("puzzleFile") or record.get("archivePuzzleName") or "<unknown>")
        by_puzzle[puzzle_key].append(record)

    puzzles = []
    total_mechanisms = 0
    total_frontier = 0

    for puzzle_key, puzzle_records in sorted(by_puzzle.items()):
        mechanisms_by_hash: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in puzzle_records:
            mechanisms_by_hash[str(record["canonicalMechanismHash"])].append(record)

        mechanisms = []
        for mechanism_hash, mechanism_records in sorted(mechanisms_by_hash.items()):
            frontier_records = pareto_frontier(mechanism_records)
            best_by_metric = {}
            for metric in METRIC_NAMES:
                candidates = [record for record in mechanism_records if _metric_value(record, metric) is not None]
                if candidates:
                    best = min(candidates, key=lambda record: (_metric_value(record, metric), str(record.get("sha256") or "")))
                    best_by_metric[metric] = _solution_ref(best)
                else:
                    best_by_metric[metric] = None

            mechanisms.append({
                "canonicalMechanismHash": mechanism_hash,
                "solutionCount": len(mechanism_records),
                "structuralVariantCount": len({record.get("canonicalStructuralHash") for record in mechanism_records if record.get("canonicalStructuralHash")}),
                "partTypes": sorted({part_type for record in mechanism_records for part_type in record.get("partTypes", [])}),
                "armCount": _range(mechanism_records, "armCount"),
                "partCount": _range(mechanism_records, "partCount"),
                "cycleSlots": _range(mechanism_records, "cycleSlots"),
                "instructionCount": _range(mechanism_records, "instructionCount"),
                "bestByMetric": best_by_metric,
                "paretoFrontier": [_solution_ref(record) for record in frontier_records],
            })
            total_frontier += len(frontier_records)

        total_mechanisms += len(mechanisms)
        puzzles.append({
            "puzzleKey": puzzle_key,
            "campaignPuzzleMatched": any(bool(record.get("campaignPuzzleMatched")) for record in puzzle_records),
            "archivePuzzleNames": sorted({str(record.get("archivePuzzleName")) for record in puzzle_records if record.get("archivePuzzleName")}),
            "solutionCount": len(puzzle_records),
            "mechanismCount": len(mechanisms),
            "mechanisms": mechanisms,
        })

    return {
        "schemaVersion": "0.1.0",
        "sourceAnalysisSchemaVersion": analysis.get("schemaVersion"),
        "summary": {
            "puzzleCount": len(puzzles),
            "solutionCount": len(parsed),
            "mechanismCount": total_mechanisms,
            "paretoRepresentativeCount": total_frontier,
        },
        "puzzles": puzzles,
    }
