from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SAFE_TASK = re.compile(r"^\.om-bridge/tasks/pending/[A-Za-z0-9._-]+\.json$")


def _changed_task(trigger_sha: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "show",
            "--pretty=format:",
            "--name-only",
            "--diff-filter=AM",
            trigger_sha,
            "--",
            ".om-bridge/tasks/pending/*.json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    candidates = [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one pending task JSON in triggering commit {trigger_sha}, found {candidates}"
        )
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--dispatch-task", default="")
    parser.add_argument("--trigger-sha", default="HEAD")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    task = (
        args.dispatch_task.strip()
        if args.event == "workflow_dispatch"
        else _changed_task(args.trigger_sha.strip() or "HEAD")
    )
    task = task.replace("\\", "/")
    if not SAFE_TASK.fullmatch(task):
        raise ValueError(f"Unsafe task path: {task}")
    if not Path(task).is_file():
        raise ValueError(f"Task file does not exist: {task}")

    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(f"task_file={task}\n")
    print(task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
