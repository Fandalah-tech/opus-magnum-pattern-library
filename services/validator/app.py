from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Opus Codex Validator", version="0.1.0")

OMSIM_BIN = os.environ.get("OMSIM_BIN", "/usr/local/bin/omsim")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
TIMEOUT_SECONDS = int(os.environ.get("OMSIM_TIMEOUT_SECONDS", "30"))


def _read_limited(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    return data


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

    # The first service version intentionally preserves upstream output.
    # Normalized metric/error parsing is delegated to the shared adapter next.
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
    return {"status": "ok", "validator": "omsim"}


@app.post("/validate")
def validate(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)

    if not puzzle_bytes or not solution_bytes:
        raise HTTPException(status_code=400, detail="Both files must contain data")

    with tempfile.TemporaryDirectory(prefix="opus-validator-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        result = _run_omsim(puzzle_path, solution_path)

    # Force serialization now so malformed output cannot escape the request.
    json.dumps(result)
    return result
