from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from packages.opus_analysis import canonical_solution_hash, solution_architecture_signature
from packages.opus_parser import parse_solution
from packages.opus_solver.portfolio_learning import solution_blueprint_parts

OBJECTIVE_FIELDS = {
    "cga": ("cycles", "cost", "area"),
    "bca": ("boundingHexagon", "cycles", "area"),
}


def _objective_key(record: dict[str, Any], objective: str) -> tuple[int, ...] | None:
    metrics = record.get(objective)
    fields = OBJECTIVE_FIELDS[objective]
    if not isinstance(metrics, dict):
        return None
    values = []
    for field in fields:
        value = metrics.get(field)
        if not isinstance(value, int):
            return None
        values.append(value)
    return tuple(values)


def _architecture_id(objective: str, mechanism_hash: str) -> str:
    return f"critelli-{objective}-{mechanism_hash[:12]}"


def select_representatives(
    records: Iterable[dict[str, Any]],
    *,
    objective: str,
    limit: int,
) -> list[dict[str, Any]]:
    eligible = [
        record for record in records
        if not record.get("showcase") and _objective_key(record, objective) is not None
    ]
    eligible.sort(key=lambda record: (
        _objective_key(record, objective),
        int(record.get("sourceRank") or 0),
        str(record.get("submissionId") or ""),
    ))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in eligible:
        mechanism_hash = str(record.get("canonicalMechanismHash") or record.get("sha256") or "")
        if not mechanism_hash:
            mechanism_hash = hashlib.sha256(
                str(record.get("file") or record.get("submissionId") or record).encode("utf-8")
            ).hexdigest()
        if mechanism_hash in seen:
            continue
        seen.add(mechanism_hash)
        selected.append(record)
        if len(selected) >= max(1, int(limit)):
            break
    return selected


def learn_critelli_metric_portfolio(
    root: Path,
    *,
    output: Path,
    representatives_per_objective: int = 8,
) -> dict[str, Any]:
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    records = []
    puzzle_files: set[str] = set()
    for source in index.get("solutions", []):
        if not source.get("file"):
            continue
        path = root / str(source["file"])
        solution = parse_solution(path)
        puzzle_file = str(solution.get("puzzleFile") or "")
        if puzzle_file:
            puzzle_files.add(puzzle_file)
        mechanism_hash = canonical_solution_hash(solution, normalize_time=True)
        records.append({
            **source,
            "canonicalMechanismHash": mechanism_hash,
            "solution": solution,
        })

    if not records:
        raise ValueError("Critelli index contains no downloadable solution records")
    if len(puzzle_files) != 1:
        raise ValueError(f"Expected one puzzle file across event solutions; found {sorted(puzzle_files)}")

    blueprints: list[dict[str, Any]] = []
    winners: dict[str, str] = {}
    objective_summaries: dict[str, Any] = {}
    seen_blueprints: dict[str, dict[str, Any]] = {}

    for objective in ("cga", "bca"):
        representatives = select_representatives(
            records,
            objective=objective,
            limit=representatives_per_objective,
        )
        if not representatives:
            raise ValueError(f"No scoring records are eligible for {objective}")
        objective_summaries[objective] = {
            "order": list(OBJECTIVE_FIELDS[objective]),
            "winnerMetricVector": representatives[0][objective],
            "representativeCount": len(representatives),
        }
        for rank, record in enumerate(representatives, start=1):
            solution = record["solution"]
            mechanism_hash = str(record["canonicalMechanismHash"])
            blueprint = seen_blueprints.get(mechanism_hash)
            if blueprint is None:
                signature = solution_architecture_signature(solution)
                blueprint = {
                    "id": _architecture_id(objective, mechanism_hash),
                    "archetype": signature["archetype"],
                    "objectives": [],
                    "objectiveRanks": {},
                    "referenceMetrics": {},
                    "architectureSignature": signature,
                    "provenance": {
                        "kind": "critelli-event-derived",
                        "eventId": index.get("eventId"),
                        "sourcePage": index.get("sourcePage"),
                        "submitter": record.get("submitter"),
                        "solutionName": record.get("solutionName"),
                        "submissionId": record.get("submissionId"),
                        "solutionSha256": record.get("sha256"),
                        "canonicalMechanismHash": mechanism_hash,
                    },
                    "parts": solution_blueprint_parts(solution),
                }
                seen_blueprints[mechanism_hash] = blueprint
                blueprints.append(blueprint)
            blueprint["objectives"].append(objective)
            blueprint["objectiveRanks"][objective] = rank
            blueprint["referenceMetrics"][objective] = record.get(objective)
            if rank == 1:
                winners[objective] = blueprint["id"]

    payload = {
        "schemaVersion": "0.1.0",
        "kind": "critelli-metric-blueprint-portfolio",
        "eventId": index.get("eventId"),
        "puzzleName": index.get("puzzleName"),
        "puzzleFile": next(iter(puzzle_files)),
        "source": {
            "kind": "critelli-event",
            "sourcePage": index.get("sourcePage"),
            "archiveUrl": index.get("archiveUrl"),
        },
        "summary": {
            "scannedSolutions": len(records),
            "scoringSolutions": sum(1 for record in records if not record.get("showcase")),
            "uniqueMechanismsInPortfolio": len(blueprints),
            "representativesPerObjective": int(representatives_per_objective),
        },
        "objectives": objective_summaries,
        "winnerArchitectureIds": winners,
        "blueprints": blueprints,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Learn compact CGA/BCA architecture representatives from a Critelli event corpus.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--representatives-per-objective", type=int, default=8)
    args = parser.parse_args()
    payload = learn_critelli_metric_portfolio(
        args.root,
        output=args.output,
        representatives_per_objective=args.representatives_per_objective,
    )
    print(json.dumps({
        "eventId": payload.get("eventId"),
        "puzzleFile": payload.get("puzzleFile"),
        "portfolioMechanisms": payload["summary"]["uniqueMechanismsInPortfolio"],
        "winners": payload["winnerArchitectureIds"],
        "objectiveWinners": {
            objective: details["winnerMetricVector"]
            for objective, details in payload["objectives"].items()
        },
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
