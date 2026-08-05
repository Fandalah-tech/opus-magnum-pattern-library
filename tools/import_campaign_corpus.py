from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

OPUSSOLVER_ARCHIVE = "https://github.com/gtw123/OpusSolver/archive/refs/heads/main.zip"
CAMPAIGN_ROOT = Path("test/puzzles/campaign")
ZLBB_BASE = "https://zlbb.faendir.com"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "opus-magnum-codex/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def import_puzzles(root: Path, force: bool = False) -> list[dict[str, Any]]:
    target = root / "puzzles"
    archive = root / "cache" / "OpusSolver-main.zip"
    extracted = root / "cache" / "OpusSolver-main"
    if force or not archive.exists():
        download(OPUSSOLVER_ARCHIVE, archive)
    if force and extracted.exists():
        shutil.rmtree(extracted)
    if not extracted.exists():
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root / "cache")

    source = extracted / CAMPAIGN_ROOT
    if not source.exists():
        raise RuntimeError(f"Campaign directory not found in archive: {source}")
    target.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*.puzzle")):
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        puzzle_id = path.stem
        records.append({
            "puzzleId": puzzle_id,
            "chapter": relative.parts[0] if len(relative.parts) > 1 else "unknown",
            "sourcePath": str(relative).replace("\\", "/"),
            "localPath": str(destination.relative_to(root)).replace("\\", "/"),
            "size": destination.stat().st_size,
            "sha256": sha256(destination),
            "leaderboardUrl": f"{ZLBB_BASE}/puzzles/{puzzle_id}",
        })
    return records


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value.strip("_") or "solution"


def import_zlbb(root: Path, puzzles: list[dict[str, Any]], limit_per_puzzle: int | None) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for ZLBB downloads. Run: pip install playwright && playwright install chromium"
        ) from exc

    output_root = root / "solutions" / "zlbb"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(30000)

        for puzzle_number, puzzle in enumerate(puzzles, start=1):
            puzzle_id = puzzle["puzzleId"]
            url = puzzle["leaderboardUrl"]
            print(f"[{puzzle_number}/{len(puzzles)}] {puzzle_id}: loading {url}", flush=True)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.locator("body").wait_for(state="attached", timeout=10000)
            except Exception as exc:
                records.append({
                    "puzzleId": puzzle_id,
                    "error": f"navigation-{type(exc).__name__}: {exc}",
                    "sourceUrl": url,
                })
                continue

            links = page.get_by_text("Download", exact=True)
            try:
                links.first.wait_for(state="attached", timeout=20000)
            except PlaywrightTimeoutError:
                records.append({
                    "puzzleId": puzzle_id,
                    "error": "no-download-links-found",
                    "sourceUrl": page.url,
                })
                continue

            count = links.count()
            if limit_per_puzzle is not None:
                count = min(count, limit_per_puzzle)
            print(f"[{puzzle_number}/{len(puzzles)}] {puzzle_id}: {count} download(s)", flush=True)

            puzzle_dir = output_root / puzzle_id
            puzzle_dir.mkdir(parents=True, exist_ok=True)
            for index in range(count):
                link = links.nth(index)
                try:
                    container_text = link.locator("xpath=ancestor::*[self::div or self::li][1]").inner_text()
                except Exception:
                    container_text = ""
                category = container_text.splitlines()[0].strip() if container_text else f"record-{index + 1}"
                try:
                    with page.expect_download(timeout=30000) as pending:
                        link.click()
                    item = pending.value
                    suggested = item.suggested_filename or f"{puzzle_id}-{index + 1}.solution"
                    filename = f"{index + 1:03d}-{_safe_name(category)}-{_safe_name(suggested)}"
                    destination = puzzle_dir / filename
                    item.save_as(destination)
                    records.append({
                        "puzzleId": puzzle_id,
                        "category": category,
                        "rankOnPage": index + 1,
                        "file": str(destination.relative_to(root)).replace("\\", "/"),
                        "size": destination.stat().st_size,
                        "sha256": sha256(destination),
                        "sourceUrl": page.url,
                    })
                except Exception as exc:
                    records.append({
                        "puzzleId": puzzle_id,
                        "category": category,
                        "rankOnPage": index + 1,
                        "error": f"download-{type(exc).__name__}: {exc}",
                        "sourceUrl": page.url,
                    })
        browser.close()
    return records


def write_index(root: Path, puzzles: list[dict[str, Any]], solutions: list[dict[str, Any]] | None = None) -> Path:
    solution_records = solutions or []
    index = {
        "schemaVersion": "0.2.0",
        "sources": {"puzzles": OPUSSOLVER_ARCHIVE, "solutions": ZLBB_BASE},
        "puzzleCount": len(puzzles),
        "solutionRecordCount": len(solution_records),
        "solutionFileCount": sum(1 for item in solution_records if item.get("file")),
        "solutionErrorCount": sum(1 for item in solution_records if item.get("error")),
        "puzzles": puzzles,
        "solutions": solution_records,
    }
    path = root / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local Opus Magnum campaign corpus.")
    parser.add_argument("--root", type=Path, default=Path(".datasets/campaign-corpus"))
    parser.add_argument("--puzzles-only", action="store_true")
    parser.add_argument("--puzzle-limit", type=int)
    parser.add_argument("--limit-per-puzzle", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    all_puzzles = import_puzzles(args.root, force=args.force)
    selected_puzzles = all_puzzles[: args.puzzle_limit] if args.puzzle_limit else all_puzzles
    solutions = None
    if not args.puzzles_only:
        solutions = import_zlbb(args.root, selected_puzzles, args.limit_per_puzzle)
    index = write_index(args.root, all_puzzles, solutions)
    print(json.dumps({
        "puzzles": len(all_puzzles),
        "puzzlesScanned": len(selected_puzzles),
        "solutionFiles": sum(1 for item in (solutions or []) if item.get("file")),
        "solutionErrors": sum(1 for item in (solutions or []) if item.get("error")),
        "index": str(index),
    }), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
