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
    ("engine-tests", [sys.executable, "-m", "pytest", "-q", "tests/test_opus_engine.py", "tests/test_disjoint_output.py", "tests/test_input_respawn.py"], 900),
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
    REPORT.write_text(json.dumps({
        "schemaVersion": 1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "stages": stages,
    }, indent=2), encoding="utf-8")


def main() -> int:
    stages: list[dict] = []
    for name, command, timeout in STAGES:
        result = run_stage(name, command, timeout)
        stages.append(result)
        write_report(stages)
        print(json.dumps({
            "stage": name,
            "exitCode": result["exitCode"],
            "durationSeconds": result["durationSeconds"],
        }), flush=True)
        # Tests and replay are safety gates. A failed tail search is still a
        # useful completed campaign because its best state is preserved.
        if name != "tail-search" and result["exitCode"] != 0:
            return result["exitCode"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
