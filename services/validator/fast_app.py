from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import app as legacy_app, _read_limited, _run_omsim

# Thin front controller for high-volume solver validation.
# Fast routes are registered on this top-level app BEFORE the legacy/static app
# is mounted, so POST /api/v1/validate cannot be intercepted by StaticFiles.
app = FastAPI(title="Opus Codex Fast Validator", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "validator": "omsim", "mode": "fast-front-controller"}


@app.post("/api/v1/validate")
def validate_only_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    """Run OMSim only; no parser graph, replay, patterns, or diagnostics."""
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)
    with tempfile.TemporaryDirectory(prefix="opus-validator-fast-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        return _run_omsim(puzzle_path, solution_path)


# Preserve every existing API/static route behind the fast front controller.
app.mount("/", legacy_app)
