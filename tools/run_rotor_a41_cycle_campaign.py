from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_engine.simulator import SimulationError
from packages.opus_parser.solution import parse_solution, parse_solution_bytes

ROOT = Path.cwd()
LIVE = ROOT / "reports" / "rotor-a41-cycle-live.json"
GENERIC_LIVE = ROOT / "reports" / "live-search-status.json"
ANALYSIS = ROOT / "reports" / "rotor-a41-cycle-analysis.json"
BEST_PARSED = ROOT / "reports" / "rotor-a41-cycle-best.parsed.json"
BEST_SOLUTION = ROOT / "reports" / "rotor-a41-cycle-best.solution"
PUZZLE = ROOT / "fixtures" / "puzzles" / "van-berlos-rotor.parsed.json"
REFERENCE_SHA = "435b31d9366f90bb5217ea45faebb392ae761fe3740050c2ffa56e847174ab47"
REFERENCE_METRICS = {"cycles": 1112, "cost": 220, "area": 41, "instructions": 302}
DEFAULT_OPUS_ROOT = Path("C:/Users/bruno/Documents/My Games/Opus Magnum")
REFERENCE_FIXTURE = ROOT / "fixtures" / "solutions" / "van-berlos-rotor-a41-1112.solution.b64"
MAX_ROUNDS = 8
MAX_CANDIDATES = 300

METRIC_IDS = {"cycles": 0, "cost": 1, "area": 2, "instructions": 3}
INSTRUCTION_BYTES = {
    "pivot_ccw": b"p", "extend": b"E", "pivot_cw": b"P", "drop": b"g",
    "track_minus": b"a", "rotate_ccw": b"r", "retract": b"e", "rotate_cw": b"R",
    "grab": b"G", "track_plus": b"A", "period_override": b"O", "reset": b"X", "repeat": b"C",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_live() -> dict[str, Any]:
    if LIVE.exists():
        return json.loads(LIVE.read_text(encoding="utf-8"))
    return {
        "schemaVersion": 3,
        "campaignId": "rotor-a41-cycle-001",
        "metrics": {
            "baseline": dict(REFERENCE_METRICS),
            "best": dict(REFERENCE_METRICS),
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
        "updatedAt": data["updatedAt"], "status": status, "stage": stage,
        "campaignId": data.get("campaignId", "rotor-a41-cycle-001"), "mode": "a41-cycle-retiming",
        "depth": data.get("round", 0), "maxDepth": MAX_ROUNDS,
        "elapsedSeconds": data.get("elapsedSeconds", 0),
        "visitedStates": metrics.get("testedCandidates", 0),
        "expandedStates": metrics.get("validCandidates", 0), "frontierSize": data.get("frontierSize", 0),
        "bestScore": best.get("cycles", baseline.get("cycles", 1112)),
        "bestPathLength": len(data.get("bestMutations", [])), "metrics": metrics, "message": message,
    }
    GENERIC_LIVE.write_text(json.dumps(generic, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_roots() -> list[Path]:
    roots: list[Path] = []
    configured = os.environ.get("OM_OPUS_MAGNUM_ROOT")
    if configured:
        roots.append(Path(configured))
    roots.extend([DEFAULT_OPUS_ROOT, ROOT / "fixtures" / "solutions", ROOT / "datasets" / "solutions", ROOT])
    for value in (os.environ.get("USERPROFILE"), "C:/Users/bruno"):
        if value:
            base = Path(value)
            roots.extend([base / "Downloads", base / "Desktop", base / "Documents"])
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key not in seen and resolved.exists():
            seen.add(key)
            unique.append(resolved)
    return unique


def _looks_like_rotor(solution: dict[str, Any]) -> bool:
    text = " ".join(str(value or "").lower() for value in (
        solution.get("puzzleFile"), solution.get("name"), solution.get("source", {}).get("name")
    ))
    return "van berlo" in text or "van-berlo" in text or "rotor" in text


def locate_local_reference() -> tuple[Path | None, str | None]:
    exact: list[Path] = []
    area_matches: list[tuple[int, int, float, Path]] = []
    for root in candidate_roots():
        try:
            for path in root.rglob("*.solution"):
                try:
                    if path.stat().st_size > 10_000_000:
                        continue
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() == REFERENCE_SHA:
                        return path, "sha256"
                    solution = parse_solution_bytes(raw, source_name=path.name)
                    if not _looks_like_rotor(solution):
                        continue
                    m = solution.get("metrics") or {}
                    if all(m.get(k) == v for k, v in REFERENCE_METRICS.items()):
                        exact.append(path)
                    elif m.get("area") == 41:
                        area_matches.append((int(m.get("cycles") or 10**9), int(m.get("instructions") or 10**9), -path.stat().st_mtime, path))
                except Exception:
                    continue
        except (OSError, PermissionError):
            continue
    if exact:
        exact.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return exact[0], "metrics"
    if area_matches:
        area_matches.sort()
        return area_matches[0][3], "area41-best-local"
    return None, None


def load_reference() -> tuple[dict[str, Any] | None, str | None, str | None]:
    path, match_kind = locate_local_reference()
    if path is not None:
        return parse_solution(path), path.name, match_kind
    if REFERENCE_FIXTURE.exists():
        raw = base64.b64decode(REFERENCE_FIXTURE.read_text(encoding="ascii"))
        solution = parse_solution_bytes(raw, source_name="van-berlos-rotor-a41-1112.solution")
        return solution, "van-berlos-rotor-a41-1112.solution", "embedded-fixture"
    return None, None, None


def candidate_shifts(solution: dict[str, Any]) -> list[dict[str, Any]]:
    shifts: list[dict[str, Any]] = []
    for part in solution.get("parts", []):
        program = sorted(part.get("program", []), key=lambda item: int(item["cycle"]))
        if not program:
            continue
        occupied = {int(item["cycle"]) for item in program}
        for item in program:
            cycle = int(item["cycle"])
            if cycle <= 0 or cycle - 1 in occupied:
                continue
            shifts.append({
                "part": part["id"], "armNumber": part.get("armNumber"),
                "cycle": cycle, "targetCycle": cycle - 1, "instruction": item["instruction"],
            })
    return shifts


def apply_shift(solution: dict[str, Any], shift: dict[str, Any]) -> dict[str, Any] | None:
    candidate = copy.deepcopy(solution)
    part = next((p for p in candidate.get("parts", []) if p.get("id") == shift["part"]), None)
    if part is None:
        return None
    if any(int(item["cycle"]) == int(shift["targetCycle"]) for item in part.get("program", [])):
        return None
    target = next((item for item in part.get("program", []) if int(item["cycle"]) == int(shift["cycle"]) and item.get("instruction") == shift["instruction"]), None)
    if target is None:
        return None
    target["cycle"] = int(shift["targetCycle"])
    part["program"] = sorted(part["program"], key=lambda item: int(item["cycle"]))
    return candidate


def is_complete(simulator: Simulator) -> bool:
    regular_ids = [output_id for output_id, *_ in simulator.output_patterns]
    repeating_ids = [output_id for output_id, *_ in simulator.repeating_patterns]
    regular_ok = all(simulator.delivered_products.get(output_id, 0) >= 6 for output_id in regular_ids)
    repeating_ok = all(simulator.repeating_product_complete(output_id, 3) for output_id in repeating_ids)
    return bool(regular_ids or repeating_ids) and regular_ok and repeating_ok


def simulate(puzzle: dict[str, Any], solution: dict[str, Any], horizon: int) -> dict[str, Any]:
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution, max_cycles=horizon)
    try:
        for row in timeline.get("cycles", []):
            instructions = {str(event["partId"]): event["instruction"] for event in row.get("events", [])}
            simulator.step(instructions)
            if is_complete(simulator):
                return {"valid": True, "completed": True, "simCycle": int(simulator.world.cycle), "error": None}
    except SimulationError as exc:
        return {"valid": False, "completed": False, "simCycle": int(simulator.world.cycle), "error": str(exc)[:1200]}
    return {"valid": False, "completed": False, "simCycle": int(simulator.world.cycle), "error": "did-not-complete"}


def _write_string(buffer: bytearray, value: str) -> None:
    raw = value.encode("utf-8")
    buffer.extend(struct.pack("<i", len(raw)))
    buffer.extend(raw)


def encode_solution(solution: dict[str, Any]) -> bytes:
    out = bytearray()
    out.extend(struct.pack("<i", int(solution.get("format", {}).get("version") or 7)))
    _write_string(out, str(solution.get("puzzleFile") or ""))
    _write_string(out, str(solution.get("name") or "OMSIM A41 cycle optimized"))
    metrics = solution.get("metrics") or {}
    metric_items = [(name, metrics.get(name)) for name in ("cycles", "cost", "area", "instructions") if metrics.get(name) is not None]
    out.extend(struct.pack("<i", len(metric_items)))
    for name, value in metric_items:
        out.extend(struct.pack("<ii", METRIC_IDS[name], int(value)))
    parts = solution.get("parts", [])
    out.extend(struct.pack("<i", len(parts)))
    for part in parts:
        _write_string(out, str(part.get("type") or ""))
        out.append(1 if part.get("enabled", True) else 0)
        pos = part.get("position") or [0, 0]
        out.extend(struct.pack("<iiiii", int(pos[0]), int(pos[1]), int(part.get("length") or 0), int(part.get("rotation") or 0), int(part.get("which") or 0)))
        program = sorted(part.get("program", []), key=lambda item: int(item["cycle"]))
        out.extend(struct.pack("<i", len(program)))
        for item in program:
            code = INSTRUCTION_BYTES.get(str(item.get("instruction")))
            if code is None:
                raw = item.get("rawCode")
                code = str(raw).encode("latin1")[:1] if isinstance(raw, str) and raw else b"?"
            out.extend(struct.pack("<i", int(item["cycle"])))
            out.extend(code)
        if part.get("type") == "track":
            cells = part.get("trackHexes", [])
            out.extend(struct.pack("<i", len(cells)))
            for q, r in cells:
                out.extend(struct.pack("<ii", int(q), int(r)))
        out.extend(struct.pack("<i", int(part.get("armNumber") or 0)))
    return bytes(out)


def save_best(solution: dict[str, Any], cycles: int, mutations: list[dict[str, Any]]) -> None:
    solution = copy.deepcopy(solution)
    solution.setdefault("metrics", {})["cycles"] = cycles
    solution["name"] = f"A41 OMSIM C{cycles}"
    solution["omsimMutations"] = mutations
    BEST_PARSED.write_text(json.dumps(solution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    BEST_SOLUTION.write_bytes(encode_solution(solution))


def main() -> int:
    started = time.monotonic()
    live = load_live()
    live["elapsedSeconds"] = 0
    publish(live, stage="reference-discovery", status="running", message="A41: chargement de la reference et du moteur OMSIM.")
    solution, reference_file, match_kind = load_reference()
    if solution is None:
        publish(live, stage="reference-required", status="blocked", message="Reference A41 introuvable localement et fixture de secours indisponible.")
        return 3
    if not PUZZLE.exists():
        publish(live, stage="puzzle-required", status="blocked", message="Puzzle Van Berlo's Rotor parse introuvable.")
        return 4
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    actual = solution.get("metrics") or {}
    if actual.get("area") != 41:
        publish(live, stage="reference-invalid", status="blocked", message=f"Reference detectee Area {actual.get('area')}, attendu 41.")
        return 5

    publish(live, stage="baseline-validation", status="running", message=f"Reference {reference_file} trouvee ({match_kind}); validation OMSIM du 1112.")
    baseline = simulate(puzzle, solution, int(REFERENCE_METRICS["cycles"]) + 24)
    if not baseline["completed"]:
        publish(live, stage="engine-validation-blocked", status="blocked", message=f"OMSIM ne reproduit pas encore la reference A41: {baseline['error']}", extra={"baselineValidation": baseline})
        return 6

    offset = int(REFERENCE_METRICS["cycles"]) - int(baseline["simCycle"])
    current = copy.deepcopy(solution)
    current_cycles = int(REFERENCE_METRICS["cycles"])
    mutations: list[dict[str, Any]] = []
    tested = 0
    valid = 0
    all_results: list[dict[str, Any]] = []
    analysis_rounds: list[dict[str, Any]] = []

    for round_index in range(1, MAX_ROUNDS + 1):
        shifts = candidate_shifts(current)
        if not shifts or tested >= MAX_CANDIDATES:
            break
        best_round: tuple[int, dict[str, Any], dict[str, Any]] | None = None
        publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: validation de {len(shifts)} retimings OMSIM.", extra={"round": round_index, "frontierSize": len(shifts), "baselineValidation": {**baseline, "cycleOffset": offset}})
        round_results = []
        for shift in shifts:
            if tested >= MAX_CANDIDATES:
                break
            candidate = apply_shift(current, shift)
            if candidate is None:
                continue
            tested += 1
            outcome = simulate(puzzle, candidate, max(24, current_cycles + 24 - offset))
            candidate_cycles = int(outcome["simCycle"]) + offset if outcome["completed"] else None
            if outcome["completed"]:
                valid += 1
            result = {"shift": shift, "valid": bool(outcome["completed"]), "cycles": candidate_cycles, "simCycle": outcome["simCycle"], "error": outcome["error"]}
            round_results.append(result)
            all_results.append(result)
            if candidate_cycles is not None and candidate_cycles < current_cycles:
                if best_round is None or candidate_cycles < best_round[0]:
                    best_round = (candidate_cycles, shift, candidate)
            metrics = live.setdefault("metrics", {})
            metrics["testedCandidates"] = tested
            metrics["validCandidates"] = valid
            live["elapsedSeconds"] = round(time.monotonic() - started, 1)
            if tested % 3 == 0 or candidate_cycles is not None and candidate_cycles < current_cycles:
                publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: {tested} testes, {valid} valides; meilleur {current_cycles} cycles.", extra={"round": round_index, "frontierSize": max(0, len(shifts) - len(round_results)), "bestMutations": mutations})
        analysis_rounds.append({"round": round_index, "sourceCycles": current_cycles, "candidates": round_results})
        if best_round is None:
            break
        current_cycles, winning_shift, current = best_round
        mutations.append(winning_shift)
        metrics = live.setdefault("metrics", {})
        metrics["best"] = {"cycles": current_cycles, "cost": 220, "area": 41, "instructions": 302}
        metrics["improvement"] = {"cycles": 1112 - current_cycles, "instructions": 0}
        metrics["testedCandidates"] = tested
        metrics["validCandidates"] = valid
        best_entry = {"rank": 1, "kind": "validated-retiming", "metrics": dict(metrics["best"]), "mutations": list(mutations)}
        live["bestResults"] = [best_entry] + [entry for entry in live.get("bestResults", []) if entry.get("kind") == "reference"][:1]
        save_best(current, current_cycles, mutations)
        publish(live, stage="improvement-found", status="running", message=f"Gain valide: {current_cycles} cycles ({1112-current_cycles} cycles sauves). Nouveau round lance.", extra={"round": round_index, "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution"})

    ANALYSIS.write_text(json.dumps({
        "schemaVersion": 2, "updatedAt": now(), "referenceFile": reference_file, "referenceMatch": match_kind,
        "baselineValidation": {**baseline, "cycleOffset": offset}, "rounds": analysis_rounds,
        "testedCandidates": tested, "validCandidates": valid, "bestCycles": current_cycles, "mutations": mutations,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    metrics = live.setdefault("metrics", {})
    metrics["testedCandidates"] = tested
    metrics["validCandidates"] = valid
    metrics["best"] = {"cycles": current_cycles, "cost": 220, "area": 41, "instructions": 302}
    metrics["improvement"] = {"cycles": 1112 - current_cycles, "instructions": 0}
    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    if current_cycles < 1112:
        save_best(current, current_cycles, mutations)
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: meilleur resultat valide {current_cycles}/220/41/302, gain {1112-current_cycles} cycles.", extra={"round": len(analysis_rounds), "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution", "analysisReport": "reports/rotor-a41-cycle-analysis.json"})
    else:
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: {tested} retimings testes, {valid} valides, aucun gain sous 1112 dans cette passe.", extra={"round": len(analysis_rounds), "frontierSize": 0, "bestMutations": mutations, "analysisReport": "reports/rotor-a41-cycle-analysis.json"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
