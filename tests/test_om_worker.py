import json
from pathlib import Path

import pytest

from tools.om_worker import _load_task, _pytest_targets


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_task_accepts_allowlisted_operation(tmp_path):
    task = _load_task(_write(tmp_path, {
        "id": "rotor-001",
        "operation": "search_rotor_structure",
        "timeout_seconds": 120,
    }))

    assert task["id"] == "rotor-001"
    assert task["timeout_seconds"] == 120


def test_load_task_rejects_shell_command(tmp_path):
    with pytest.raises(ValueError, match="unknown task fields"):
        _load_task(_write(tmp_path, {
            "id": "unsafe",
            "operation": "search_rotor_structure",
            "command": "Remove-Item C:\\*",
        }))


def test_load_task_rejects_unknown_operation(tmp_path):
    with pytest.raises(ValueError, match="unsupported operation"):
        _load_task(_write(tmp_path, {"id": "unsafe", "operation": "shell"}))


def test_pytest_targets_must_stay_under_tests(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task = {
        "operation": "run_tests",
        "pytest_targets": ["../tools/om_worker.py"],
    }
    with pytest.raises(ValueError, match="unsafe pytest target"):
        _pytest_targets(task)
