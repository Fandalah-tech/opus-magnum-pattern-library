from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import ssl
import urllib.error
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


def _stream_download(url: str, destination: Path, *, insecure_tls: bool = False) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "opus-magnum-codex/1.0"})
    context = ssl._create_unverified_context() if insecure_tls else None
    with urllib.request.urlopen(request, timeout=180, context=context) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    try:
        _stream_download(url, temporary)
    except urllib.error.URLError as exc:
        if "TLSV1_UNRECOGNIZED_NAME" not in str(exc).upper():
            raise
        print(f"TLS/SNI retry without certificate verification: {url}", flush=True)
        temporary.unlink(missing_ok=True)
        _stream_download(url, temporary, insecure_tls=True)
    temporary.replace(destination)


def write_index(root: Path, records: list[dict[str, Any]]) -> Path:
    total_puzzles = sum(int(item.get("puzzleCount", 0)) for item in records)
    index = {
        "schemaVersion": "0.2.0",
        "datasetCount": len(records),
        "successfulDatasetCount": sum(1 for item in records if item.get("status") == "complete"),
        "failedDatasetCount": sum(1 for item in records if item.get("status") == "error"),
        "puzzleCount": total_puzzles,
        "datasets": records,
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / "index.json"
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and inventory external puzzle-only corpora from datasets/registry.json")
    parser.add_argument("--registry", type=Path, default=Path("datasets/registry.json"))
    parser.add_argument("--root", type=Path, default=Path(".datasets/external-corpus"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if any dataset fails.")
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    selected = [
        item for item in registry.get("datasets", [])
        if item.get("kind") == "puzzles" and "external-download" in item.get("intendedUse", [])
    ]

    records: list[dict[str, Any]] = []
    failures = 0
    for dataset in selected:
        dataset_id = str(dataset["id"])
        source = str(dataset["source"])
        dataset_root = args.root / dataset_id
        archive = args.root / "archives" / f"{dataset_id}.zip"
        extract_root = dataset_root / "files"
        record: dict[str, Any] = {
            "id": dataset_id,
            "title": dataset.get("title"),
            "source": source,
            "sourcePage": dataset.get("sourcePage"),
            "author": dataset.get("author"),
            "license": dataset.get("license"),
            "status": "error",
            "puzzleCount": 0,
            "puzzles": [],
        }
        try:
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
                puzzles.append({
                    "file": path.relative_to(args.root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                })
            record.update({
                "status": "complete",
                "archive": archive.relative_to(args.root).as_posix(),
                "archiveSize": archive.stat().st_size,
                "archiveSha256": sha256(archive),
                "puzzleCount": len(puzzles),
                "puzzles": puzzles,
            })
            print(json.dumps({"dataset": dataset_id, "puzzles": len(puzzles), "status": "complete"}), flush=True)
        except Exception as exc:
            failures += 1
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(json.dumps({"dataset": dataset_id, "status": "error", "error": record["error"]}), flush=True)
        records.append(record)
        write_index(args.root, records)

    index_path = write_index(args.root, records)
    print(json.dumps({
        "datasets": len(records),
        "successfulDatasets": len(records) - failures,
        "failedDatasets": failures,
        "puzzles": sum(int(item.get("puzzleCount", 0)) for item in records),
        "index": str(index_path),
    }), flush=True)
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
