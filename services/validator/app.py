from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from packages.opus_analysis import analyze_solution, build_program_timeline, build_solution_graph, detect_patterns
from packages.opus_parser import ParseError, parse_puzzle_bytes, parse_solution_bytes

API_VERSION = "1.0.0"
app = FastAPI(title="Opus Codex Validator", version=API_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

OMSIM_BIN = os.environ.get("OMSIM_BIN", "/usr/local/bin/omsim")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
TIMEOUT_SECONDS = int(os.environ.get("OMSIM_TIMEOUT_SECONDS", "30"))


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


def _bundle(model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    graph = build_solution_graph(model)
    timeline = build_program_timeline(model)
    patterns = detect_patterns(model, graph, timeline)
    diagnostics = analyze_solution(model, graph, timeline, patterns)
    return graph, timeline, patterns, diagnostics


def _run_omsim(puzzle_path: Path, solution_path: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [OMSIM_BIN, str(puzzle_path), str(solution_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="omsim binary is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Validation timed out") from exc

    raw = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return {
        "schemaVersion": "0.1.0",
        "validator": {
            "name": "omsim",
            "version": None,
            "commit": os.environ.get("OMSIM_COMMIT"),
        },
        "valid": completed.returncode == 0,
        "metrics": {"cost": None, "cycles": None, "area": None, "instructions": None},
        "issues": [] if completed.returncode == 0 else [{
            "severity": "error",
            "code": "OMSIM_VALIDATION_FAILED",
            "message": raw or f"omsim exited with code {completed.returncode}",
        }],
        "knownDivergence": False,
        "rawOutput": raw,
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

    graph, timeline, patterns, diagnostics = _bundle(solution_model)
    return {
        "schemaVersion": "1.0.0",
        "apiVersion": API_VERSION,
        "puzzle": puzzle_model,
        "solution": solution_model,
        "validation": validation,
        "graph": graph,
        "timeline": timeline,
        "patterns": patterns,
        "diagnostics": diagnostics,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "validator": "omsim", "apiVersion": API_VERSION}


@app.post("/api/v1/analyze")
def analyze_pair_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    result = _analyze_pair(puzzle, solution)
    json.dumps(result)
    return result


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


@app.post("/analyze/patterns")
def analyze_patterns_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    model = _canonical_parse(parse_solution_bytes, solution)
    graph, timeline, patterns, _ = _bundle(model)
    return {**patterns, "inputs": {"graph": graph["summary"], "timeline": timeline["summary"]}}


@app.post("/analyze/diagnostics")
def analyze_diagnostics_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    model = _canonical_parse(parse_solution_bytes, solution)
    graph, timeline, patterns, diagnostics = _bundle(model)
    return {
        **diagnostics,
        "inputs": {
            "graph": graph["summary"],
            "timeline": timeline["summary"],
            "patterns": patterns["summary"],
        },
    }


@app.post("/validate")
def validate(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    result = _analyze_pair(puzzle, solution)
    validation = result["validation"]
    validation["puzzle"] = {
        "name": result["puzzle"]["name"],
        "sha256": result["puzzle"]["source"]["sha256"],
        "production": result["puzzle"]["production"],
    }
    validation["solution"] = {
        "name": result["solution"]["name"],
        "sha256": result["solution"]["source"]["sha256"],
        "declaredMetrics": result["solution"]["metrics"],
        "partCount": len(result["solution"]["parts"]),
    }
    validation["analysis"] = {
        "structuralGraph": result["graph"]["summary"],
        "programTimeline": result["timeline"]["summary"],
        "patterns": result["patterns"]["summary"],
        "diagnostics": result["diagnostics"]["summary"],
    }
    return validation
