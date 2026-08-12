from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Iterable

from packages.opus_analysis import (
    puzzle_feature_fingerprint,
    puzzle_feature_payload,
    solution_architecture_signature,
)
from packages.opus_parser.solution_writer import write_solution_bytes

from .objective_portfolio import OBJECTIVES, objective_key


def _solution_fingerprint(solution: dict[str, Any]) -> str:
    return hashlib.sha256(write_solution_bytes(solution)).hexdigest()


def _program_tape(
    program: Iterable[dict[str, Any]],
    *,
    chunk_size: int = 12,
) -> list[str]:
    tokens = [
        f"{int(item.get('cycle') or 0)}:{str(item.get('instruction') or '')}"
        for item in sorted(program, key=lambda item: int(item.get("cycle") or 0))
    ]
    return [" ".join(tokens[index:index + chunk_size]) for index in range(0, len(tokens), chunk_size)]


def solution_blueprint_parts(solution: dict[str, Any]) -> list[dict[str, Any]]:
    """Strip file identity and compact a solution into a materializable topology."""

    parts: list[dict[str, Any]] = []
    for source in solution.get("parts") or ():
        part = {
            "type": str(source.get("type") or ""),
            "position": [int(value) for value in (source.get("position") or (0, 0))],
            "rotation": int(source.get("rotation") or 0),
            "length": int(source.get("length") or 1),
            "which": int(source.get("which") or 0),
            "armNumber": int(source.get("armNumber") or 0),
        }
        program = list(source.get("program") or ())
        if program:
            if len(program) <= 24:
                part["program"] = [
                    {
                        "cycle": int(item.get("cycle") or 0),
                        "instruction": str(item.get("instruction") or ""),
                    }
                    for item in program
                ]
            else:
                part["programTape"] = _program_tape(program)
        if source.get("trackHexes"):
            part["trackHexes"] = [
                [int(value) for value in cell]
                for cell in source["trackHexes"]
            ]
        if source.get("type") == "pipe":
            part["pipeId"] = int(source.get("pipeId") or 0)
            part["pipeHexes"] = [
                [int(value) for value in cell]
                for cell in source.get("pipeHexes") or ()
            ]
        parts.append(part)
    return parts


def _eligible(record: dict[str, Any], objective: str) -> bool:
    metrics = record.get("metrics") or {}
    required = ("cost", "cycles", "area", "instructions")
    if not all(isinstance(metrics.get(key), int) for key in required):
        return False
    return objective != "rate" or isinstance(metrics.get("rate"), int)


def learn_objective_blueprint_portfolio(
    puzzle: dict[str, Any],
    records: Iterable[dict[str, Any]],
    *,
    puzzle_strategy: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Learn the objective winners from scored, externally held solutions.

    Raw corpus files are not embedded.  Only the distinct winning topologies,
    their authoritative metrics, hashes, and provenance are retained.
    """

    candidates = [record for record in records if record.get("valid", True)]
    winners: dict[str, dict[str, Any]] = {}
    for objective in OBJECTIVES:
        eligible = [record for record in candidates if _eligible(record, objective)]
        if not eligible:
            raise ValueError(f"No fully scored solution is eligible for objective {objective!r}")
        winners[objective] = min(
            eligible,
            key=lambda record: (
                objective_key(objective, record["metrics"]),
                str(record.get("sourcePath") or record.get("sourceName") or ""),
            ),
        )

    objectives_by_fingerprint: dict[str, list[str]] = {}
    record_by_fingerprint: dict[str, dict[str, Any]] = {}
    for objective, record in winners.items():
        solution = record["solution"]
        fingerprint = _solution_fingerprint(solution)
        objectives_by_fingerprint.setdefault(fingerprint, []).append(objective)
        record_by_fingerprint[fingerprint] = record

    blueprints: list[dict[str, Any]] = []
    architecture_by_fingerprint: dict[str, str] = {}
    for fingerprint in sorted(
        record_by_fingerprint,
        key=lambda value: min(OBJECTIVES.index(item) for item in objectives_by_fingerprint[value]),
    ):
        record = record_by_fingerprint[fingerprint]
        solution = record["solution"]
        signature = solution_architecture_signature(solution)
        architecture_id = f"{signature['archetype']}-{fingerprint[:10]}"
        architecture_by_fingerprint[fingerprint] = architecture_id
        provenance = deepcopy(record.get("provenance") or {})
        provenance.setdefault("kind", "external-corpus-derived")
        provenance.setdefault("sourceName", record.get("sourceName"))
        provenance["solutionSha256"] = fingerprint
        blueprints.append({
            "id": architecture_id,
            "archetype": signature["archetype"],
            "objectives": objectives_by_fingerprint[fingerprint],
            "provenance": provenance,
            "referenceMetrics": deepcopy(record["metrics"]),
            "architectureSignature": signature,
            "parts": solution_blueprint_parts(solution),
        })

    baseline_record = winners["sum4"]
    baseline_fingerprint = _solution_fingerprint(baseline_record["solution"])
    return {
        "schemaVersion": "0.2.0",
        "kind": "objective-blueprint-portfolio",
        "puzzleStrategy": puzzle_strategy,
        "puzzleFeatureFingerprint": puzzle_feature_fingerprint(puzzle),
        "puzzleFeaturePayload": puzzle_feature_payload(puzzle),
        "source": deepcopy(source),
        "baselineArchitectureId": architecture_by_fingerprint[baseline_fingerprint],
        "blueprints": blueprints,
    }


def bounded_worker_count(requested: int | None, *, cpu_count: int | None) -> int:
    available = max(1, int(cpu_count or 1))
    desired = available if requested is None else max(1, int(requested))
    return min(10, available, desired)
