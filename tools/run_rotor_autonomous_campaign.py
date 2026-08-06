from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
REPORT = ROOT / "reports" / "rotor-autonomous-campaign.json"

STAGES = [
    (
        "engine-tests",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_engine_disjoint.py",
            "tests/test_disjoint_output_consumer.py",
            "tests/test_input_component_respawn.py",
        ],
        900,
    ),
    ("strict-replay", [sys.executable, "tools/report_rotor_strict_replay.py"], 900),
    ("tail-search", [sys.executable, "tools/search_rotor_last_atom_tail.py"], 6000),
]


def run_stage(name: str, command: list[str], timeout: int) -> dict:
    started = datetime.now(timezone.utc)
    tick = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=None,
            check=False,
        )
        return {
            "name": name,
            "command": command,
            "startedAt": started.isoformat(),
            "durationSeconds": round(time.monotonic() - tick, 3),
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "command": command,
            "startedAt": started.isoformat(),
            "durationSeconds": round(time.monotonic() - tick, 3),
            "exitCode": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\nTIMEOUT\n",
        }


def write_report(stages: list[dict]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "stages": stages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    stages: list[dict] = []
    for name, command, timeout in STAGES:
        result = run_stage(name, command, timeout)
        stages.append(result)
        write_report(stages)
        print(
            json.dumps(
                {
                    "stage": name,
                    "exitCode": result["exitCode"],
                    "durationSeconds": result["durationSeconds"],
                }
            ),
            flush=True,
        )
        if result["exitCode"] != 0:
            if result["stdout"]:
                print(f"--- {name} stdout ---\n{result['stdout']}", flush=True)
            if result["stderr"]:
                print(f"--- {name} stderr ---\n{result['stderr']}", file=sys.stderr, flush=True)
        if name != "tail-search" and result["exitCode"] != 0:
            return result["exitCode"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
