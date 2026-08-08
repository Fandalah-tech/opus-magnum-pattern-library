from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import File, UploadFile

from app import app, _analyze_pair, _read_limited, _run_omsim


def _validate_bytes(puzzle: UploadFile, solution: UploadFile) -> dict[str, Any]:
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)
    with tempfile.TemporaryDirectory(prefix="opus-validator-fast-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        return _run_omsim(puzzle_path, solution_path)


@app.post("/api/v1/validate")
def validate_only_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    """Fast OMSim-only validation endpoint for high-volume solver searches."""
    return _validate_bytes(puzzle, solution)


# app.py mounted the static site before this module was imported, so move the
# new route before the catch-all mount.
fast_validate_route = app.router.routes.pop()
mount_index = next(
    (i for i, route in enumerate(app.router.routes) if getattr(route, "path", None) == "/"),
    len(app.router.routes),
)
app.router.routes.insert(mount_index, fast_validate_route)


@app.post("/api/v1/analyze")
def solver_aware_analyze_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    """Keep full analysis for interactive clients, but fast-path solver variants.

    The evolutionary solver already calls /api/v1/analyze and expects a
    top-level ``validation`` object. Variant files are therefore validated by
    OMSim only while preserving the existing response shape, so currently
    installed agents gain the speedup without a client update.
    """
    name = (solution.filename or "").lower()
    if name.startswith("variant-") or name.startswith("candidate-"):
        return {"validation": _validate_bytes(puzzle, solution), "fastPath": True}
    return _analyze_pair(puzzle, solution)


solver_analyze_route = app.router.routes.pop()
original_analyze_index = next(
    (
        i
        for i, route in enumerate(app.router.routes)
        if getattr(route, "path", None) == "/api/v1/analyze"
    ),
    mount_index,
)
app.router.routes.insert(original_analyze_index, solver_analyze_route)
