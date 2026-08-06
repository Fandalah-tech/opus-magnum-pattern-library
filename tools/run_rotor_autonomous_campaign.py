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
            "tests/test_input_source_components.py",
        ],
        900,
    ),
    ("strict-replay", [sys.executable, "tools/report_rotor_strict_replay.py"], 900),
    ("tail-search", [sys.executable, "tools/search_rotor_last_atom_tail.py"], 6000),
]


def run_stage(name: str, command: list[str], timeout: int) -> dict:
    started = datetime.now(timezone.utc)
    tick = time.monotonic()
    output_lines: list[str] = []
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    try:
        assert process.stdout is not None
        while True:
            if time.monotonic() - tick >= timeout:
                process.kill()
                output_lines.append("TIMEOUT\n")
                process.wait()
                exit_code = 124
                break
            line = process.stdout.readline()
            if line:
                output_lines.append(line)
                print(f"[{name}] {line}", end="", flush=True)
                continue
            exit_code = process.poll()
            if exit_code is not None:
                break
            time.sleep(0.1)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    return {
        "name": name,
        "command": command,
        "startedAt": started.isoformat(),
        "durationSeconds": round(time.monotonic() - tick, 3),
        "exitCode": exit_code,
        "stdout": "".join(output_lines),
        "stderr": "",
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
        print(json.dumps({"stage": name, "status": "started"}), flush=True)
        result = run_stage(name, command, timeout)
        stages.append(result)
        write_report(stages)
        print(
            json.dumps(
                {
                    "stage": name,
                    "status": "finished",
                    "exitCode": result["exitCode"],
                    "durationSeconds": result["durationSeconds"],
                }
            ),
            flush=True,
        )
        if name != "tail-search" and result["exitCode"] != 0:
            return result["exitCode"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
