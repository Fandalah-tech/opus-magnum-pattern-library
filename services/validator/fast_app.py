from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import File, UploadFile

from app import app, _read_limited, _run_omsim


@app.post("/api/v1/validate")
def validate_only_endpoint(
    puzzle: UploadFile = File(...),
    solution: UploadFile = File(...),
) -> dict[str, Any]:
    """Fast OMSim-only validation endpoint for high-volume solver searches.

    Unlike /api/v1/analyze and the legacy /validate route, this endpoint does
    not build parser models, graphs, timelines, replays, patterns, or
    diagnostics. It only materializes the two files and invokes OMSim.
    """
    puzzle_bytes = _read_limited(puzzle)
    solution_bytes = _read_limited(solution)
    with tempfile.TemporaryDirectory(prefix="opus-validator-fast-") as temp_dir:
        root = Path(temp_dir)
        puzzle_path = root / "input.puzzle"
        solution_path = root / "input.solution"
        puzzle_path.write_bytes(puzzle_bytes)
        solution_path.write_bytes(solution_bytes)
        return _run_omsim(puzzle_path, solution_path)


# app.py mounts the static site at '/'. The decorator above appends the fast
# route after that mount, so move the new route before the catch-all mount.
fast_route = app.router.routes.pop()
insert_at = next(
    (i for i, route in enumerate(app.router.routes) if getattr(route, "path", None) == "/"),
    len(app.router.routes),
)
app.router.routes.insert(insert_at, fast_route)
