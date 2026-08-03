from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from packages.opus_analysis import build_program_timeline, build_solution_graph, detect_patterns
from packages.opus_parser import ParseError, parse_puzzle_bytes, parse_solution_bytes

app = FastAPI(title="Opus Codex Validator", version="0.5.0")
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
    return data


def _canonical_parse(parser, upload: UploadFile) -> dict[str, Any]:
    data = _read_limited(upload)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        return parser(data, source_name=upload.filename)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _analysis_bundle(solution_model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    graph = build_solution_graph(solution_model)
    timeline = build_program_timeline(solution_model)
    patterns = detect_patterns(solution_model, graph, timeline)
    return graph, timeline, patterns


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

    raw_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return {
        "schemaVersion": "0.1.0",
        "validator": {"name": "omsim", "version": None, "commit": os.environ.get("OMSIM_COMMIT")},
        "valid": completed.returncode == 0,
        "metrics": {"cost": None, "cycles": None, "area": None, "instructions": None},
        "issues": [] if completed.returncode == 0 else [{
            "severity": "error",
            "code": "OMSIM_VALIDATION_FAILED",
            "message": raw_output or f"omsim exited with code {completed.returncode}",
        }],
        "knownDivergence": False,
        "rawOutput": raw_output,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "validator": "omsim", "apiVersion": "0.5.0"}


@app.post("/parse/puzzle")
def parse_puzzle_endpoint(puzzle: UploadFile = File(...)) -> dict[str, Any]:
    return _canonical_parse(parse_puzzle_bytes, puzzle)


@app.post("/parse/solution")
def parse_solution_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    return _canonical_parse(parse_solution_bytes, solution)


@app.post("/analyze/graph")
def analyze_graph_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    return build_solution_graph(solution_model)


@app.post("/analyze/timeline")
def analyze_timeline_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    return build_program_timeline(solution_model)


@app.post("/analyze/patterns")
def analyze_patterns_endpoint(solution: UploadFile = File(...)) -> dict[str, Any]:
    solution_model = _canonical_parse(parse_solution_bytes, solution)
    graph, timeline, patterns = _analysis_bundle(solution_model)
    return {
        **patterns,
        "inputs": {
            "graph": graph["summary"],
            "timeline": timeline["summary"],
        },
    }


@app.post("/validate")
def validate(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)
    if not puzzle_bytes or not solution_bytes:
        raise HTTPException(status_code=400, detail="Both files must contain data")

    try:
        puzzle_model = parse_puzzle_bytes(puzzle_bytes, source_name=puzzle.filename)
        solution_model = parse_solution_bytes(solution_bytes, source_name=solution.filename)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="opus-validator-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        result = _run_omsim(puzzle_path, solution_path)

    graph, timeline, patterns = _analysis_bundle(solution_model)
    result["puzzle"] = {
        "name": puzzle_model["name"],
        "sha256": puzzle_model["source"]["sha256"],
        "production": puzzle_model["production"],
    }
    result["solution"] = {
        "name": solution_model["name"],
        "sha256": solution_model["source"]["sha256"],
        "declaredMetrics": solution_model["metrics"],
        "partCount": len(solution_model["parts"]),
    }
    result["analysis"] = {
        "structuralGraph": graph["summary"],
        "programTimeline": timeline["summary"],
        "patterns": patterns["summary"],
    }
    json.dumps(result)
    return result
