#!/usr/bin/env python3
"""Inventory external Opus Magnum datasets without redistributing their contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TRACKED_SUFFIXES = {".puzzle", ".solution", ".txt", ".json", ".zip"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, dataset_id: str) -> dict:
    files = []
    suffix_counts: Counter[str] = Counter()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        suffix = path.suffix.lower() or "<none>"
        suffix_counts[suffix] += 1
        if suffix in TRACKED_SUFFIXES:
            files.append({
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "type": suffix,
            })

    return {
        "schemaVersion": "0.1.0",
        "datasetId": dataset_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "totalFiles": sum(suffix_counts.values()),
        "countsByExtension": dict(sorted(suffix_counts.items())),
        "trackedFiles": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"Dataset directory does not exist: {args.root}")

    result = inventory(args.root.resolve(), args.dataset_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "datasetId": result["datasetId"],
        "totalFiles": result["totalFiles"],
        "countsByExtension": result["countsByExtension"],
        "trackedFiles": len(result["trackedFiles"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
