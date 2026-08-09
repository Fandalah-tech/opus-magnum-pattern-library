from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

SOURCE_REPO = "https://github.com/F43nd1r/om-archive"
SOURCE_ARCHIVE = SOURCE_REPO + "/archive/refs/heads/main.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "opus-magnum-codex/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory the public F43nd1r Opus Magnum solution archive.")
    parser.add_argument("--root", type=Path, default=Path(".datasets/solution-archive"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root
    archive = root / "archives" / "f43nd1r-om-archive-main.zip"
    extract_root = root / "files"

    if args.force or not archive.exists():
        print(f"Downloading {SOURCE_ARCHIVE}", flush=True)
        download(SOURCE_ARCHIVE, archive)

    if args.force and extract_root.exists():
        shutil.rmtree(extract_root)

    if not extract_root.exists():
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extract_root)

    solutions = []
    chapter_counts: Counter[str] = Counter()
    puzzle_counts: Counter[str] = Counter()
    seen_hashes: Counter[str] = Counter()

    for path in sorted(extract_root.rglob("*.solution")):
        rel_to_extract = path.relative_to(extract_root)
        parts = rel_to_extract.parts
        # The GitHub archive adds an om-archive-main/ prefix.
        logical = parts[1:] if parts and parts[0].startswith("om-archive-") else parts
        chapter = logical[0] if len(logical) >= 1 else "unknown"
        puzzle = logical[1] if len(logical) >= 2 else "unknown"
        digest = sha256(path)
        chapter_counts[chapter] += 1
        puzzle_counts[puzzle] += 1
        seen_hashes[digest] += 1
        solutions.append({
            "file": path.relative_to(root).as_posix(),
            "sourcePath": "/".join(logical),
            "chapter": chapter,
            "puzzleName": puzzle,
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": digest,
        })

    duplicate_hashes = {digest: count for digest, count in seen_hashes.items() if count > 1}
    index = {
        "schemaVersion": "0.1.0",
        "source": SOURCE_REPO,
        "sourceArchive": SOURCE_ARCHIVE,
        "archiveSize": archive.stat().st_size,
        "archiveSha256": sha256(archive),
        "solutionCount": len(solutions),
        "uniqueSolutionHashes": len(seen_hashes),
        "duplicateHashCount": len(duplicate_hashes),
        "puzzleNameCount": len(puzzle_counts),
        "chapterCounts": dict(sorted(chapter_counts.items())),
        "puzzleCounts": dict(sorted(puzzle_counts.items())),
        "solutions": solutions,
    }
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    print(json.dumps({
        "solutions": len(solutions),
        "uniqueSolutionHashes": len(seen_hashes),
        "puzzles": len(puzzle_counts),
        "duplicateHashCount": len(duplicate_hashes),
        "index": str(index_path),
    }), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
