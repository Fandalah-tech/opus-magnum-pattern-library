from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_TIMEOUT_SECONDS = 6 * 60 * 60
ALLOWED_OPERATIONS: dict[str, list[str]] = {
    "run_tests": [sys.executable, "-m", "pytest", "-q"],
    "diagnose_local_opus_access": [sys.executable, "tools/diagnose_local_opus_access.py"],
    "run_reference_regression": [sys.executable, "tools/run_reference_regression.py", "--manifest", "fixtures/reference/campaign-p007-p015.manifest.json", "--fixtures", ".private-fixtures/files", "--validator-url", "https://opus-validator-6gflgqb25q-nn.a.run.app", "--output", "reports/campaign-p007-p015-local.json"],
    "search_rotor_structure": [sys.executable, "tools/search_rotor_structure.py"],
    "search_rotor_half_geometry": [sys.executable, "tools/search_rotor_half_geometry.py"],
    "probe_rotor_half_moves": [sys.executable, "tools/probe_rotor_half_moves.py"],
    "validate_reference_macro_replay": [sys.executable, "tools/validate_reference_macro_replay.py"],
    "report_rotor_area46_fragments": [sys.executable, "tools/report_rotor_area46_fragments.py"],
    "solve_rotor_area47_chemistry": [sys.executable, "tools/solve_rotor_area47_chemistry.py"],
    "solve_rotor_area47_near_complete": [sys.executable, "tools/solve_rotor_area47_near_complete.py"],
    "solve_rotor_area47_final_chemistry": [sys.executable, "tools/solve_rotor_area47_final_chemistry.py"],
    "report_rotor_van_berlo_duplication": [sys.executable, "tools/report_rotor_van_berlo_duplication.py"],
    "report_rotor_baron_contacts": [sys.executable, "tools/report_rotor_baron_contacts.py"],
    "report_rotor_solution_layout": [sys.executable, "tools/report_rotor_solution_layout.py"],
    "report_rotor_duplication_cells": [sys.executable, "tools/report_rotor_duplication_cells.py"],
    "report_rotor_atom_trajectories": [sys.executable, "tools/report_rotor_atom_trajectories.py"],
    "report_rotor_almost_solved_tail": [sys.executable, "tools/report_rotor_almost_solved_tail.py"],
    "report_rotor_prefix": [sys.executable, "tools/report_rotor_prefix.py"],
    "report_rotor_macros": [sys.executable, "tools/report_rotor_macros.py"],
    "report_rotor_strict_replay": [sys.executable, "tools/report_rotor_strict_replay.py"],
    "report_rotor_respawn_models": [sys.executable, "tools/report_rotor_respawn_models.py"],
    "search_rotor_last_atom_tail": [sys.executable, "tools/search_rotor_last_atom_tail.py"],
    "run_rotor_autonomous_campaign": [sys.executable, "tools/run_rotor_autonomous_campaign.py"],
    "run_rotor_a41_cycle_campaign": [sys.executable, "tools/run_rotor_a41_cycle_campaign.py"],
    "run_rotor_a41_remote_cycle_campaign": [sys.executable, "tools/run_rotor_a41_remote_cached.py"],
    "analyze_a41_retiming_results": [sys.executable, "tools/analyze_a41_retiming_results.py"],
    "build_rotor_candidate_replay": [sys.executable, "tools/build_rotor_candidate_replay.py"],
    "apply_rotor_bonder_chain_patch": [sys.executable, "tools/apply_rotor_bonder_chain_patch.py"],
    "import_critelli_liquid_perfumes": [sys.executable, "tools/import_critelli_event.py", "--max-solutions", "25", "--delay", "0.4"],
}


def _load_task(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("task must be a JSON object")
    allowed_keys = {"id", "operation", "priority", "timeout_seconds", "pytest_targets", "notes"}
    unknown = set(data) - allowed_keys
    if unknown:
        raise ValueError(f"unknown task fields: {sorted(unknown)}")
    task_id = data.get("id")
    if not isinstance(task_id, str) or not task_id or not all(ch.isalnum() or ch in "._-" for ch in task_id):
        raise ValueError("task id must use only letters, digits, dot, underscore, and hyphen")
    operation = data.get("operation")
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported operation: {operation!r}")
    priority = int(data.get("priority", 0))
    if priority < -10000 or priority > 10000:
        raise ValueError("priority must be between -10000 and 10000")
    data["priority"] = priority
    timeout = int(data.get("timeout_seconds", 900))
    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    data["timeout_seconds"] = timeout
    return data


def _pytest_targets(task: dict[str, Any]) -> list[str]:
    targets = task.get("pytest_targets", [])
    if not targets:
        return []
    if task["operation"] != "run_tests":
        raise ValueError("pytest_targets is only valid for run_tests")
    if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
        raise ValueError("pytest_targets must be a list of strings")
    safe: list[str] = []
    for item in targets:
        normalized = item.replace("\\", "/")
        if not normalized.startswith("tests/") or ".." in normalized or not normalized.endswith(".py"):
            raise ValueError(f"unsafe pytest target: {item}")
        if not Path(normalized).is_file():
            raise ValueError(f"pytest target does not exist: {item}")
        safe.append(normalized)
    return safe


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def _pending_count() -> int | None:
    try:
        pending = Path(".om-bridge/tasks/pending")
        return len(list(pending.glob("*.json"))) if pending.is_dir() else 0
    except Exception:
        return None


def _write_agent_status(*, task: dict[str, Any] | None, task_id: str, started_at: datetime, finished_at: datetime, duration_seconds: float, exit_code: int, error: str | None) -> None:
    reports = Path("reports")
    reports.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "status": "idle" if exit_code == 0 else "task-failed",
        "desired_state": "running",
        "current_task": None,
        "last_task": task_id,
        "last_operation": task.get("operation") if task else None,
        "last_priority": task.get("priority") if task else None,
        "last_result": "success" if exit_code == 0 else "failed",
        "last_exit_code": exit_code,
        "last_error": error,
        "last_started_at": started_at.isoformat(),
        "last_finished_at": finished_at.isoformat(),
        "last_duration_seconds": duration_seconds,
        "pending_tasks": _pending_count(),
        "runner_name": os.environ.get("RUNNER_NAME") or os.environ.get("COMPUTERNAME"),
        "git_sha": _git_sha(),
        "heartbeat": finished_at.isoformat(),
        "message": f"Dernière tâche: {task_id} — {'succès' if exit_code == 0 else 'échec'} ({duration_seconds:.1f}s)",
    }
    (reports / "om-agent-status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one allow-listed OMSIM research task.")
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--results-root", required=True, type=Path)
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    task: dict[str, Any] | None = None
    exit_code = 1
    stdout = ""
    stderr = ""
    error: str | None = None
    try:
        task = _load_task(args.task)
        command = [*ALLOWED_OPERATIONS[task["operation"]], *_pytest_targets(task)]
        completed = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, timeout=task["timeout_seconds"], env={**os.environ, "PYTHONPATH": str(Path.cwd())}, check=False)
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        error = "operation timed out"
    except Exception as exc:
        exit_code = 2
        error = f"{type(exc).__name__}: {exc}"
        stderr = error + "\n"
    task_id = task.get("id") if task else args.task.stem
    result_dir = args.results_root / str(task_id)
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (result_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    finished_at = datetime.now(timezone.utc)
    duration_seconds = round(time.monotonic() - started, 3)
    summary = {"schema_version": 1, "task": task, "task_file": args.task.as_posix(), "git_sha": _git_sha(), "runner_name": os.environ.get("RUNNER_NAME") or os.environ.get("COMPUTERNAME"), "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(), "duration_seconds": duration_seconds, "exit_code": exit_code, "status": "success" if exit_code == 0 else "failed", "error": error}
    (result_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_agent_status(task=task, task_id=str(task_id), started_at=started_at, finished_at=finished_at, duration_seconds=duration_seconds, exit_code=exit_code, error=error)
    print(json.dumps(summary, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
