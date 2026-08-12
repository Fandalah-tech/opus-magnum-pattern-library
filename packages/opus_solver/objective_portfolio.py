from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from packages.opus_engine.builder import rotate_hex
from packages.opus_parser.solution_writer import write_solution_bytes

from .manufacturing import ManufacturingPlan, build_manufacturing_plan
from .solver import (
    UnsupportedPuzzleError,
    _generate_parallel_fragment_extraction_solution,
    _puzzle_file_id,
    validate_generated_solution,
)


OBJECTIVES = (
    "cost",
    "area",
    "cycles",
    "rate",
    "instructions",
    "costarea",
    "costcycles",
    "sum4",
)

_BLUEPRINT_PATH = Path(__file__).with_name("data") / "sos_objective_blueprints.json"


@dataclass(slots=True)
class ObjectiveCandidate:
    architecture_id: str
    archetype: str
    focus_objectives: tuple[str, ...]
    provenance: dict[str, Any]
    reference_metrics: dict[str, int]
    solution: dict[str, Any]
    local_validation: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(write_solution_bytes(self.solution)).hexdigest()

    def to_dict(self, *, include_solution: bool = False) -> dict[str, Any]:
        result = {
            "architectureId": self.architecture_id,
            "archetype": self.archetype,
            "focusObjectives": list(self.focus_objectives),
            "provenance": deepcopy(self.provenance),
            "referenceMetrics": deepcopy(self.reference_metrics),
            "fingerprint": self.fingerprint,
            "localValidation": deepcopy(self.local_validation),
        }
        if include_solution:
            result["solution"] = deepcopy(self.solution)
        return result


@lru_cache(maxsize=1)
def _objective_blueprints() -> tuple[dict[str, Any], ...]:
    payload = json.loads(_BLUEPRINT_PATH.read_text(encoding="utf-8"))
    if payload.get("puzzleStrategy") != "corpus-derived-fragment-extraction-v1":
        raise ValueError(f"Unexpected objective blueprint strategy in {_BLUEPRINT_PATH}")
    blueprints = tuple(payload.get("blueprints") or ())
    if not blueprints:
        raise ValueError(f"No objective blueprints found in {_BLUEPRINT_PATH}")
    return blueprints


def _transformed_part(
    source: dict[str, Any],
    *,
    architecture_id: str,
    index: int,
    rotation: int,
    translation: tuple[int, int],
) -> dict[str, Any]:
    position = rotate_hex(tuple(source.get("position") or (0, 0)), rotation)
    program = [
        {
            "cycle": int(item.get("cycle") or 0),
            "instruction": str(item.get("instruction") or ""),
        }
        for item in source.get("program") or ()
    ]
    for chunk in source.get("programTape") or ():
        for token in str(chunk).split():
            cycle, instruction = token.split(":", 1)
            program.append({"cycle": int(cycle), "instruction": instruction})
    program.sort(key=lambda item: item["cycle"])
    part = {
        "id": f"{architecture_id}-part-{index}",
        "type": str(source.get("type") or ""),
        "enabled": True,
        "position": [position[0] + translation[0], position[1] + translation[1]],
        "length": int(source.get("length") or 1),
        "rotation": (int(source.get("rotation") or 0) + rotation) % 6,
        "which": int(source.get("which") or 0),
        "armNumber": int(source.get("armNumber") or 0),
        "program": program,
    }
    if source.get("trackHexes"):
        part["trackHexes"] = [
            list(rotate_hex(tuple(cell), rotation))
            for cell in source["trackHexes"]
        ]
    return part


def _materialize_blueprint(
    puzzle: dict[str, Any],
    blueprint: dict[str, Any],
    *,
    variant_index: int,
) -> dict[str, Any]:
    architecture_id = str(blueprint["id"])
    rotation = (variant_index + 2) % 6
    translation = (18 + variant_index * 3, 11 - variant_index * 2)
    parts = [
        _transformed_part(
            source,
            architecture_id=architecture_id,
            index=index,
            rotation=rotation,
            translation=translation,
        )
        for index, source in enumerate(blueprint.get("parts") or ())
    ]
    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {
            "name": None,
            "generator": "opus_solver/objective-architecture-portfolio-v1",
            "architectureId": architecture_id,
            "provenanceKind": str((blueprint.get("provenance") or {}).get("kind") or ""),
        },
        "puzzleFile": _puzzle_file_id(puzzle),
        "name": f"Opus Solver - {architecture_id}",
        "metrics": {},
        "unknownMetrics": [],
        "parts": parts,
        "trailingBytes": 0,
    }


def _candidate(
    puzzle: dict[str, Any],
    *,
    architecture_id: str,
    archetype: str,
    focus_objectives: Iterable[str],
    provenance: dict[str, Any],
    reference_metrics: dict[str, int],
    solution: dict[str, Any],
) -> ObjectiveCandidate:
    return ObjectiveCandidate(
        architecture_id=architecture_id,
        archetype=archetype,
        focus_objectives=tuple(focus_objectives),
        provenance=deepcopy(provenance),
        reference_metrics={key: int(value) for key, value in reference_metrics.items()},
        solution=solution,
        local_validation=validate_generated_solution(puzzle, solution),
    )


def generate_objective_candidates(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan | None = None,
) -> tuple[ObjectiveCandidate, ...]:
    """Generate independent architectures for objective-scored oracle search.

    The candidates are deliberately returned even when the local simulator
    reports a divergence.  OMSim is the authoritative oracle for the portfolio
    workflow, while the local result remains attached as a diagnostic.
    """

    resolved_plan = plan or build_manufacturing_plan(puzzle)
    if not resolved_plan.supported:
        raise UnsupportedPuzzleError(
            resolved_plan.reason or "Puzzle is not supported by the current solver"
        )
    if resolved_plan.strategy != "corpus-derived-fragment-extraction-v1":
        raise UnsupportedPuzzleError(
            "Objective portfolios are not registered for strategy " + resolved_plan.strategy
        )

    balanced = _generate_parallel_fragment_extraction_solution(puzzle, resolved_plan)
    candidates = [
        _candidate(
            puzzle,
            architecture_id="balanced-sum4-v1",
            archetype="balanced-cell",
            focus_objectives=("costcycles", "sum4"),
            provenance={"kind": "public-corpus-derived", "sourceName": "generated topology at 9bcd370"},
            reference_metrics={"cost": 145, "cycles": 95, "area": 84, "instructions": 19},
            solution=balanced,
        )
    ]
    for index, blueprint in enumerate(_objective_blueprints()):
        solution = _materialize_blueprint(puzzle, blueprint, variant_index=index)
        candidates.append(
            _candidate(
                puzzle,
                architecture_id=str(blueprint["id"]),
                archetype=str(blueprint["archetype"]),
                focus_objectives=blueprint.get("objectives") or (),
                provenance=blueprint.get("provenance") or {},
                reference_metrics=blueprint.get("referenceMetrics") or {},
                solution=solution,
            )
        )
    return tuple(candidates)


def objective_key(objective: str, metrics: dict[str, Any]) -> tuple[int, ...]:
    if objective not in OBJECTIVES:
        raise ValueError(f"Unknown objective {objective!r}; expected one of {OBJECTIVES}")

    fallback = 10**12
    cost = int(metrics.get("cost")) if isinstance(metrics.get("cost"), int) else fallback
    area = int(metrics.get("area")) if isinstance(metrics.get("area"), int) else fallback
    cycles = int(metrics.get("cycles")) if isinstance(metrics.get("cycles"), int) else fallback
    instructions = (
        int(metrics.get("instructions"))
        if isinstance(metrics.get("instructions"), int)
        else fallback
    )
    rate = int(metrics.get("rate")) if isinstance(metrics.get("rate"), int) else fallback

    keys = {
        "cost": (cost, area, cycles, instructions),
        "area": (area, cost, cycles, instructions),
        "cycles": (cycles, rate, cost, area, instructions),
        "rate": (rate, cycles, cost, area, instructions),
        "instructions": (instructions, cost, area, cycles),
        "costarea": (cost * area, cost, area, cycles, instructions),
        "costcycles": (cost + cycles, cost, cycles, area, instructions),
        "sum4": (cost + cycles + area + instructions, cost, cycles, area, instructions),
    }
    return keys[objective]


def select_objective_winners(
    records: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    valid = [record for record in records if record.get("oracleValidation", {}).get("valid")]
    if not valid:
        return {}
    return {
        objective: min(
            valid,
            key=lambda record: (
                objective_key(objective, record["metrics"]),
                str(record.get("architectureId") or ""),
            ),
        )
        for objective in OBJECTIVES
    }
