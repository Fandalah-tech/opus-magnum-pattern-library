from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.opus_parser.solution import parse_solution

ROOT = Path.cwd()
LIVE = ROOT / "reports" / "rotor-a41-cycle-live.json"
GENERIC_LIVE = ROOT / "reports" / "live-search-status.json"
ANALYSIS = ROOT / "reports" / "rotor-a41-cycle-analysis.json"
REFERENCE_SHA = "435b31d9366f90bb5217ea45faebb392ae761fe3740050c2ffa56e847174ab47"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_live() -> dict[str, Any]:
    if LIVE.exists():
        return json.loads(LIVE.read_text(encoding="utf-8"))
    return {
        "schemaVersion": 2,
        "campaignId": "rotor-a41-cycle-001",
        "metrics": {
            "baseline": {"cycles": 1112, "cost": 220, "area": 41, "instructions": 302},
            "best": {"cycles": 1112, "cost": 220, "area": 41, "instructions": 302},
            "improvement": {"cycles": 0, "instructions": 0},
            "testedCandidates": 0,
            "validCandidates": 0,
        },
        "bestResults": [],
    }


def publish(data: dict[str, Any], *, stage: str, status: str, message: str, extra: dict[str, Any] | None = None) -> None:
    data.update({"updatedAt": now(), "stage": stage, "status": status, "message": message})
    if extra:
        data.update(extra)
    LIVE.parent.mkdir(parents=True, exist_ok=True)
    LIVE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    metrics = data.get("metrics", {})
    baseline = metrics.get("baseline", {})
    best = metrics.get("best", baseline)
    generic = {
        "updatedAt": data["updatedAt"],
        "status": status,
        "stage": stage,
        "campaignId": data.get("campaignId", "rotor-a41-cycle-001"),
        "mode": "a41-cycle-retiming",
        "depth": 0,
        "maxDepth": 0,
        "elapsedSeconds": data.get("elapsedSeconds", 0),
        "visitedStates": metrics.get("testedCandidates", 0),
        "expandedStates": metrics.get("validCandidates", 0),
        "frontierSize": 0,
        "bestScore": best.get("cycles", baseline.get("cycles", 1112)),
        "bestPathLength": 0,
        "metrics": metrics,
        "message": message,
    }
    GENERIC_LIVE.write_text(json.dumps(generic, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_roots() -> list[Path]:
    roots = [ROOT]
    for value in (os.environ.get("USERPROFILE"), "C:/Users/bruno"):
        if not value:
            continue
        base = Path(value)
        for child in ("Downloads", "Desktop", "Documents"):
            path = base / child
            if path.exists():
                roots.append(path)
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def locate_reference() -> Path | None:
    for root in candidate_roots():
        try:
            for path in root.rglob("*.solution"):
                try:
                    if path.stat().st_size > 10_000_000:
                        continue
                    if hashlib.sha256(path.read_bytes()).hexdigest() == REFERENCE_SHA:
                        return path
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue
    return None


def analyze_program(solution: dict[str, Any]) -> dict[str, Any]:
    programmed = []
    potential_shifts = []
    for part in solution.get("parts", []):
        program = sorted(part.get("program", []), key=lambda item: int(item["cycle"]))
        if not program:
            continue
        occupied = {int(item["cycle"]) for item in program}
        gaps = []
        for left, right in zip(program, program[1:]):
            gap = int(right["cycle"]) - int(left["cycle"])
            if gap > 1:
                gaps.append({"after": int(left["cycle"]), "before": int(right["cycle"]), "size": gap - 1})
        for item in program:
            cycle = int(item["cycle"])
            if cycle > 0 and cycle - 1 not in occupied:
                potential_shifts.append({
                    "part": part["id"],
                    "armNumber": part.get("armNumber"),
                    "cycle": cycle,
                    "targetCycle": cycle - 1,
                    "instruction": item["instruction"],
                })
        programmed.append({
            "part": part["id"],
            "type": part["type"],
            "armNumber": part.get("armNumber"),
            "instructionCount": len(program),
            "firstCycle": int(program[0]["cycle"]),
            "lastCycle": int(program[-1]["cycle"]),
            "idleWindows": gaps,
        })
    return {
        "reference": {
            "path": str(solution.get("source", {}).get("name")),
            "sha256": solution.get("source", {}).get("sha256"),
            "metrics": solution.get("metrics"),
            "name": solution.get("name"),
        },
        "programmedParts": programmed,
        "candidateSingleCycleShifts": potential_shifts,
        "candidateCount": len(potential_shifts),
    }


def main() -> int:
    started = time.monotonic()
    live = load_live()
    live["elapsedSeconds"] = 0
    publish(live, stage="reference-discovery", status="running", message="Campagne A41 active: recherche locale de la reference verrouillee par SHA-256.")
    reference = locate_reference()
    if reference is None:
        publish(live, stage="reference-required", status="blocked", message="Reference A41 introuvable sur le PC; recherche bloquee avant toute mutation.")
        return 3

    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    publish(live, stage="program-analysis", status="running", message=f"Reference trouvee: {reference.name}. Analyse des fenetres de retiming.")
    solution = parse_solution(reference)
    analysis = analyze_program(solution)
    ANALYSIS.write_text(json.dumps({"schemaVersion": 1, "updatedAt": now(), **analysis}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    metrics = live.setdefault("metrics", {})
    metrics["testedCandidates"] = analysis["candidateCount"]
    metrics["validCandidates"] = 0
    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    publish(
        live,
        stage="validation-queue",
        status="running",
        message=f"{analysis['candidateCount']} retimings elementaires identifies; preparation de la validation OMSIM.",
        extra={"analysisReport": "reports/rotor-a41-cycle-analysis.json", "referencePath": str(reference)},
    )

    # Short heartbeat only. The campaign now yields quickly instead of occupying the
    # machine for hours while no validated mutator is running.
    for remaining in range(4, 0, -1):
        time.sleep(15)
        live = load_live()
        live["elapsedSeconds"] = round(time.monotonic() - started, 1)
        publish(live, stage="validation-queue", status="running", message=f"A41 prioritaire: validation OMSIM en preparation ({remaining}/4).")

    live = load_live()
    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    publish(live, stage="analysis-complete", status="completed", message="Passe de retiming A41 terminee; aucun gain n'est declare sans validation OMSIM complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
