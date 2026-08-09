from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "opus-magnum-codex/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and inventory external puzzle-only corpora from datasets/registry.json")
    parser.add_argument("--registry", type=Path, default=Path("datasets/registry.json"))
    parser.add_argument("--root", type=Path, default=Path(".datasets/external-corpus"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    selected = [
        item for item in registry.get("datasets", [])
        if item.get("kind") == "puzzles" and "external-download" in item.get("intendedUse", [])
    ]

    records: list[dict[str, Any]] = []
    total_puzzles = 0
    for dataset in selected:
        dataset_id = str(dataset["id"])
        source = str(dataset["source"])
        dataset_root = args.root / dataset_id
        archive = args.root / "archives" / f"{dataset_id}.zip"
        extract_root = dataset_root / "files"

        if args.force or not archive.exists():
            print(f"Downloading {dataset_id}: {source}", flush=True)
            download(source, archive)

        if args.force and extract_root.exists():
            shutil.rmtree(extract_root)
        if not extract_root.exists():
            extract_root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extract_root)

        puzzles = []
        for path in sorted(extract_root.rglob("*.puzzle")):
            rel = path.relative_to(args.root).as_posix()
            puzzles.append({
                "file": rel,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            })
        total_puzzles += len(puzzles)
        record = {
            "id": dataset_id,
            "title": dataset.get("title"),
            "source": source,
            "sourcePage": dataset.get("sourcePage"),
            "author": dataset.get("author"),
            "license": dataset.get("license"),
            "archive": archive.relative_to(args.root).as_posix(),
            "archiveSize": archive.stat().st_size,
            "archiveSha256": sha256(archive),
            "puzzleCount": len(puzzles),
            "puzzles": puzzles,
        }
        records.append(record)
        print(json.dumps({"dataset": dataset_id, "puzzles": len(puzzles)}), flush=True)

    index = {
        "schemaVersion": "0.1.0",
        "datasetCount": len(records),
        "puzzleCount": total_puzzles,
        "datasets": records,
    }
    args.root.mkdir(parents=True, exist_ok=True)
    index_path = args.root / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(json.dumps({"datasets": len(records), "puzzles": total_puzzles, "index": str(index_path)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
