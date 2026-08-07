from __future__ import annotations

import getpass
import json
import os
import platform
from pathlib import Path


def inspect_path(path: Path) -> dict:
    result = {
        "path": str(path),
        "exists": path.exists(),
        "isDir": path.is_dir(),
        "puzzles": [],
        "solutions": [],
        "error": None,
    }
    if not path.exists() or not path.is_dir():
        return result
    try:
        result["puzzles"] = [str(p) for p in path.rglob("*.puzzle")][:200]
        result["solutions"] = [str(p) for p in path.rglob("*.solution")][:200]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    userprofile = os.environ.get("USERPROFILE")
    candidates = [
        Path(r"C:\Users\bruno\Documents\My Games\Opus Magnum"),
        Path.home() / "Documents" / "My Games" / "Opus Magnum",
    ]
    if userprofile:
        candidates.append(Path(userprofile) / "Documents" / "My Games" / "Opus Magnum")

    unique = []
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)

    report = {
        "computer": platform.node(),
        "python": platform.python_version(),
        "getpassUser": getpass.getuser(),
        "environment": {
            "USERNAME": os.environ.get("USERNAME"),
            "USERPROFILE": userprofile,
            "HOMEDRIVE": os.environ.get("HOMEDRIVE"),
            "HOMEPATH": os.environ.get("HOMEPATH"),
            "RUNNER_NAME": os.environ.get("RUNNER_NAME"),
            "OM_OPUS_MAGNUM_ROOT": os.environ.get("OM_OPUS_MAGNUM_ROOT"),
        },
        "home": str(Path.home()),
        "paths": [inspect_path(path) for path in unique],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
