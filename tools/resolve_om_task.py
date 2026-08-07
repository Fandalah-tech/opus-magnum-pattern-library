from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SAFE_TASK = re.compile(r"^\.om-bridge/tasks/pending/[A-Za-z0-9._-]+\.json$")


def _changed_task(trigger_sha: str, *, allow_empty: bool = False) -> str:
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
    if not candidates and allow_empty:
        return ""
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one added/modified pending task JSON in triggering commit {trigger_sha}, found {candidates}"
        )
    return candidates[0]


def _write_output(path: Path, *, task_file: str, has_task: bool) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"task_file={task_file}\n")
        stream.write(f"has_task={'true' if has_task else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--dispatch-task", default="")
    parser.add_argument("--trigger-sha", default="HEAD")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    task = (
        args.dispatch_task.strip()
        if args.event == "workflow_dispatch"
        else _changed_task(
            args.trigger_sha.strip() or "HEAD",
            allow_empty=args.allow_empty,
        )
    )
    task = task.replace("\\", "/")

    if not task:
        if not args.allow_empty:
            raise ValueError("No pending task resolved")
        _write_output(args.output, task_file="", has_task=False)
        print("No added/modified pending task in triggering commit; skipping local worker.")
        return 0

    if not SAFE_TASK.fullmatch(task):
        raise ValueError(f"Unsafe task path: {task}")
    if not Path(task).is_file():
        if args.allow_empty:
            _write_output(args.output, task_file="", has_task=False)
            print(f"Pending task no longer exists in checkout; skipping: {task}")
            return 0
        raise ValueError(f"Task file does not exist: {task}")

    _write_output(args.output, task_file=task, has_task=True)
    print(task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
