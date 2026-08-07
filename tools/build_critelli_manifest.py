from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def stable_id(prefix: str, digest: str) -> str:
    value = str(digest or "").strip().lower()
    if len(value) < 16:
        raise ValueError(f"Invalid SHA-256 for {prefix}: {digest!r}")
    return f"{prefix}-{value[:16]}"


def build(event_catalog: dict, solution_catalog: dict | None = None) -> dict:
    solution_events = {e["eventUrl"]: e for e in (solution_catalog or {}).get("events", [])}
    puzzles: list[dict] = []
    solutions: list[dict] = []
    puzzle_ids: dict[str, str] = {}
    seen_solutions: set[str] = set()

    for event in event_catalog.get("events", []):
        puzzle = event.get("puzzle") or {}
        digest = puzzle.get("sha256")
        if not digest:
            continue
        puzzle_id = stable_id("puz", digest)
        puzzle_ids[digest] = puzzle_id
        puzzles.append({
            "id": puzzle_id,
            "sha256": digest,
            "name": event.get("puzzleTitle") or puzzle.get("file") or puzzle_id,
            "file": puzzle.get("file"),
            "size": puzzle.get("bytes"),
            "sourceDataset": "critelli-public-events",
            "sourceUrl": event.get("eventUrl"),
            "eventTitle": event.get("eventTitle"),
            "eventAuthor": event.get("author"),
            "eventEnded": event.get("ended"),
            "metricsText": event.get("metricsText") or [],
            "submissionsUrl": event.get("submissionsUrl"),
            "publicSubmissionCount": (event.get("submissions") or {}).get("count"),
            "redistribution": "metadata-only",
            "validation": {"puzzleHash": "verified-from-inline-bytes"},
            "tags": ["critelli", "public-event"],
        })

        enriched = solution_events.get(event.get("eventUrl")) or {}
        for solution in enriched.get("solutions", []):
            sdigest = solution.get("sha256")
            if not sdigest or sdigest in seen_solutions:
                continue
            seen_solutions.add(sdigest)
            solutions.append({
                "id": stable_id("sol", sdigest),
                "sha256": sdigest,
                "puzzleId": puzzle_id,
                "file": solution.get("downloadName"),
                "name": solution.get("solutionName"),
                "version": solution.get("formatVersion"),
                "size": solution.get("bytes"),
                "metrics": solution.get("metrics") or {},
                "partCount": solution.get("partCount"),
                "sourceDataset": "critelli-public-events",
                "sourceUrl": solution.get("sourceUrl"),
                "redistribution": "metadata-only",
                "validation": {
                    "parserClean": solution.get("trailingBytes") == 0,
                    "embeddedMetrics": all(v is not None for v in (solution.get("metrics") or {}).values()),
                    "omsim": None,
                },
                "tags": ["critelli", "public-submission"],
            })

    puzzles.sort(key=lambda x: ((x.get("name") or "").casefold(), x["id"]))
    solutions.sort(key=lambda x: (x["puzzleId"], (x.get("metrics") or {}).get("cycles") or 10**12, x["id"]))
    return {
        "schemaVersion": "0.1.0",
        "id": "critelli-public-events",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "redistribution": "metadata-only",
        "source": {
            "description": "Public Opus Magnum event metadata and public submission metadata discovered from events.critelli.technology.",
            "filesCommitted": False,
            "notes": "Puzzle and solution binaries are not redistributed. SHA-256 and parsed metadata are retained; solution binaries are downloaded ephemerally only when enrichment is run.",
        },
        "summary": {
            "puzzleCount": len(puzzles),
            "enrichedSolutionCount": len(solutions),
            "puzzlesWithPublicSubmissions": sum(1 for p in puzzles if p.get("submissionsUrl")),
            "discoveredPublicSolutionLinks": sum(int(p.get("publicSubmissionCount") or 0) for p in puzzles),
        },
        "puzzles": puzzles,
        "solutions": solutions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Critelli crawl/enrichment reports into a canonical metadata manifest.")
    ap.add_argument("--events", type=Path, default=Path("reports/critelli-event-catalog.json"))
    ap.add_argument("--solutions", type=Path, default=Path("reports/critelli-liquid-perfumes-solutions.json"))
    ap.add_argument("--output", type=Path, default=Path("database/critelli-public-events.manifest.json"))
    args = ap.parse_args()
    events = json.loads(args.events.read_text(encoding="utf-8"))
    solutions = json.loads(args.solutions.read_text(encoding="utf-8")) if args.solutions.exists() else None
    manifest = build(events, solutions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
