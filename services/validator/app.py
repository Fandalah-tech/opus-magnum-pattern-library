from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from packages.opus_analysis import (
    analyze_solution,
    build_program_timeline,
    build_replay_trace,
    build_solution_graph,
    detect_patterns,
)
from packages.opus_engine import Simulator, compare_replays
from packages.opus_parser import ParseError, parse_puzzle_bytes, parse_solution_bytes
from packages.opus_validator import build_command, classify_result

API_VERSION = "1.9.0"
app = FastAPI(title="Opus Codex Validator", version=API_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

OMSIM_BIN = os.environ.get("OMSIM_BIN", "/usr/local/bin/omsim")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
TIMEOUT_SECONDS = int(os.environ.get("OMSIM_TIMEOUT_SECONDS", "30"))
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", "/app/static"))


def _read_limited(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    if not data:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'Uploaded file'} is empty")
    return data


def _parse_bytes(parser, data: bytes, source_name: str | None) -> dict[str, Any]:
    try:
        return parser(data, source_name=source_name)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _canonical_parse(parser, upload: UploadFile) -> dict[str, Any]:
    return _parse_bytes(parser, _read_limited(upload), upload.filename)


def _visual_molecules(world: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    atoms_by_id = {
        str(atom.get("id")): atom
        for atom in world.get("atoms", [])
        if atom.get("id") is not None
    }
    visual: list[dict[str, Any]] = []
    atom_to_molecule: dict[str, str] = {}

    for component in world.get("molecules", []):
        atom_ids = sorted(str(atom_id) for atom_id in component.get("atomIds", []))
        if not atom_ids:
            continue
        molecule_id = f"engine-molecule-{atom_ids[0]}"
        component_ids = set(atom_ids)
        atoms = []
        holders: set[str] = set()
        for atom_id in atom_ids:
            atom = atoms_by_id.get(atom_id)
            if atom is None:
                continue
            atoms.append({
                "id": atom_id,
                "element": atom.get("element"),
                "position": list(atom.get("position") or (0, 0)),
            })
            holders.update(str(holder) for holder in atom.get("heldBy", []))
            atom_to_molecule[atom_id] = molecule_id

        bonds = []
        for bond in world.get("bonds", []):
            first_id = str(bond.get("fromAtomId"))
            second_id = str(bond.get("toAtomId"))
            if first_id not in component_ids or second_id not in component_ids:
                continue
            first = atoms_by_id.get(first_id)
            second = atoms_by_id.get(second_id)
            if first is None or second is None:
                continue
            kind = str(bond.get("type") or "normal")
            edge = sorted((first_id, second_id))
            bonds.append({
                "id": f"engine-bond-{edge[0]}-{edge[1]}-{kind}",
                "type": kind,
                "fromAtomId": first_id,
                "toAtomId": second_id,
                "from": list(first.get("position") or (0, 0)),
                "to": list(second.get("position") or (0, 0)),
            })

        visual.append({
            "id": molecule_id,
            "source": "opus-engine",
            "heldBy": [{"partId": holder} for holder in sorted(holders)],
            "atoms": atoms,
            "bonds": bonds,
        })
    return visual, atom_to_molecule


def _visual_engine_replay(puzzle: dict[str, Any], solution: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    simulator = Simulator.from_models(puzzle, solution)
    raw = simulator.run_timeline(timeline)
    frames: list[dict[str, Any]] = []

    for index, frame in enumerate(raw.get("frames", [])):
        molecules, atom_to_molecule = _visual_molecules(frame.get("world", {}))
        arm_states = []
        for arm in frame.get("arms", []):
            state = dict(arm)
            state["heldMoleculeIds"] = sorted({
                atom_to_molecule.get(str(item.get("atomId")))
                for item in arm.get("heldAtoms", [])
                if atom_to_molecule.get(str(item.get("atomId")))
            })
            arm_states.append(state)

        events = []
        for event in frame.get("events", []):
            normalized = dict(event)
            if normalized.get("partId") is None and normalized.get("armId") is not None:
                normalized["partId"] = normalized.get("armId")
            events.append(normalized)

        initial = index == 0 or frame.get("phase") == "initial"
        display_cycle = 0 if initial else int(frame.get("cycle") or index)
        frames.append({
            "cycle": int(frame.get("cycle") or 0),
            "displayCycle": display_cycle,
            "phase": frame.get("phase"),
            "phaseLabel": "initial" if initial else "after-instructions",
            "armStates": arm_states,
            "molecules": molecules,
            "events": events,
            "world": frame.get("world", {}),
        })

    raw_summary = raw.get("summary", {})
    requested_cycles = int(raw_summary.get("requestedCycles") or len(timeline.get("cycles", [])))
    return {
        "schemaVersion": "0.3.0",
        "traceType": "opus-engine-visual",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": requested_cycles,
            "completedCycles": int(raw_summary.get("completedCycles") or max(0, len(frames) - 1)),
            "terminatedWithError": bool(raw_summary.get("terminatedWithError")),
        },
        "capabilities": {
            "physicalArmAnimation": True,
            "moleculeAnimation": True,
            "multiBranchGrab": True,
            "bondState": True,
            "elementTransmutation": True,
            "engineReplay": True,
        },
        "frames": frames,
    }


def _bundle(puzzle: dict[str, Any], solution: dict[str, Any], *, replay_cycles: int | None = None):
    graph = build_solution_graph(solution)
    timeline = build_program_timeline(solution, max_cycles=replay_cycles)
    replay = _visual_engine_replay(puzzle, solution, timeline)
    patterns = detect_patterns(solution, graph, timeline)
    diagnostics = analyze_solution(solution, graph, timeline, patterns)
    return graph, timeline, replay, patterns, diagnostics


def _run_omsim(puzzle_path: Path, solution_path: Path) -> dict[str, Any]:
    command = build_command(OMSIM_BIN, puzzle_path, solution_path)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="omsim binary is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Validation timed out") from exc
    raw = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    classified = classify_result(completed.returncode, raw)
    return {
        "schemaVersion": "0.2.0",
        "validator": {"name": "omsim", "version": None, "commit": os.environ.get("OMSIM_COMMIT")},
        **classified,
        "knownDivergence": False,
        "rawOutput": raw,
        "execution": {"exitCode": completed.returncode, "timeoutSeconds": TIMEOUT_SECONDS, "interface": "--puzzle-file"},
    }


def _analyze_pair(puzzle: UploadFile, solution: UploadFile) -> dict[str, Any]:
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)
    puzzle_model = _parse_bytes(parse_puzzle_bytes, puzzle_bytes, puzzle.filename)
    solution_model = _parse_bytes(parse_solution_bytes, solution_bytes, solution.filename)
    with tempfile.TemporaryDirectory(prefix="opus-validator-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        validation = _run_omsim(puzzle_path, solution_path)
    validated_cycles = validation.get("metrics", {}).get("cycles")
    replay_cycles = int(validated_cycles) if isinstance(validated_cycles, (int, float)) and validated_cycles > 0 else None
    graph, timeline, replay, patterns, diagnostics = _bundle(puzzle_model, solution_model, replay_cycles=replay_cycles)
    return {
        "schemaVersion": "1.9.0", "apiVersion": API_VERSION, "puzzle": puzzle_model,
        "solution": solution_model, "validation": validation, "graph": graph,
        "timeline": timeline, "replay": replay, "patterns": patterns, "diagnostics": diagnostics,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "validator": "omsim", "apiVersion": API_VERSION}


@app.post("/api/v1/analyze")
def analyze_pair_endpoint(puzzle: UploadFile = File(...), solution: UploadFile = File(...)) -> dict[str, Any]:
    result = _analyze_pair(puzzle, solution)
    json.dumps(result)
    return result


@app.post("/api/v1/replay")
def replay_endpoint(puzzle: UploadFile = File(...), solution: UploadFile = File(...)) -> dict[str, Any]:
    puzzle_model = _canonical_parse(parse_puzzle_bytes, puzzle)
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    timeline = build_program_timeline(solution_model)
    return _visual_engine_replay(puzzle_model, solution_model, timeline)


@app.post("/api/v1/replay/legacy")
def legacy_replay_endpoint(puzzle: UploadFile = File(...), solution: UploadFile = File(...)) -> dict[str, Any]:
    puzzle_model = _canonical_parse(parse_puzzle_bytes, puzzle)
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    timeline = build_program_timeline(solution_model)
    return build_replay_trace(puzzle_model, solution_model, timeline)


@app.post("/api/v1/engine/replay")
def experimental_engine_replay_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    puzzle_model = _canonical_parse(parse_puzzle_bytes, puzzle)
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    timeline = build_program_timeline(solution_model)
    simulator = Simulator.from_models(puzzle_model, solution_model)
    return simulator.run_timeline(timeline)


@app.post("/api/v1/engine/compare")
def experimental_engine_compare_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    puzzle_model = _canonical_parse(parse_puzzle_bytes, puzzle)
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    timeline = build_program_timeline(solution_model)
    legacy = build_replay_trace(puzzle_model, solution_model, timeline)
    simulator = Simulator.from_models(puzzle_model, solution_model)
    try:
        engine = simulator.run_timeline(timeline)
    except Exception as exc:
        return {
            "schemaVersion": "0.1.0",
            "status": "engine-error",
            "errorType": type(exc).__name__,
            "message": str(exc),
            "completedFrameCount": len(simulator.frames),
        }
    return compare_replays(legacy, engine)


@app.post("/parse/puzzle")
def parse_puzzle_endpoint(puzzle: UploadFile = File(...)) -> dict[str, Any]:
    return _canonical_parse(parse_puzzle_bytes, puzzle)


@app.post("/parse/solution")
def parse_solution_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    return _canonical_parse(parse_solution_bytes, solution)


@app.post("/analyze/graph")
def analyze_graph_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    return build_solution_graph(_canonical_parse(parse_solution_bytes, solution))


@app.post("/analyze/timeline")
def analyze_timeline_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    return build_program_timeline(_canonical_parse(parse_solution_bytes, solution))


@app.post("/validate")
def validate(puzzle: UploadFile = File(...), solution: UploadFile = File(...)) -> dict[str, Any]:
    return _analyze_pair(puzzle, solution)["validation"]


# Registered last so API and OpenAPI routes keep priority over the static app.
if STATIC_ROOT.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_ROOT, html=True), name="codex-static")
