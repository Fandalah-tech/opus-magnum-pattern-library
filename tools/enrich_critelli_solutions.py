from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from packages.opus_parser.solution import parse_solution_bytes
from tools.import_critelli_event import fetch


def choose_events(catalog: dict, event_url: str | None) -> list[dict]:
    events = [e for e in catalog.get("events", []) if (e.get("submissions") or {}).get("solutions")]
    if event_url:
        events = [e for e in events if e.get("eventUrl") == event_url]
    return events


def enrich_solution(event: dict, source: dict) -> dict:
    data, content_type = fetch(source["url"])
    parsed = parse_solution_bytes(data, source_name=source.get("downloadName"))
    return {
        "downloadName": source.get("downloadName"),
        "sourceUrl": source["url"],
        "contentType": content_type,
        "sha256": parsed["source"]["sha256"],
        "bytes": parsed["source"]["size"],
        "formatVersion": parsed["format"]["version"],
        "puzzleFile": parsed["puzzleFile"],
        "solutionName": parsed["name"],
        "metrics": parsed["metrics"],
        "partCount": len(parsed["parts"]),
        "trailingBytes": parsed["trailingBytes"],
        "eventPuzzleSha256": (event.get("puzzle") or {}).get("sha256"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Download public Critelli solutions ephemerally and retain metadata only.")
    ap.add_argument("--catalog", type=Path, default=Path("reports/critelli-event-catalog.json"))
    ap.add_argument("--output", type=Path, default=Path("reports/critelli-solution-catalog.json"))
    ap.add_argument("--event-url", default="", help="Optional exact Critelli event URL for a pilot run.")
    ap.add_argument("--delay", type=float, default=0.10, help="Delay between solution downloads.")
    ap.add_argument("--max-solutions", type=int, default=0, help="0 means every solution in selected events.")
    args = ap.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    events = choose_events(catalog, args.event_url or None)
    records: list[dict] = []
    failures: list[dict] = []
    seen_hashes: dict[str, dict] = {}
    attempted = 0

    for event in events:
        event_records: list[dict] = []
        sources = (event.get("submissions") or {}).get("solutions") or []
        for source in sources:
            if args.max_solutions > 0 and attempted >= args.max_solutions:
                break
            attempted += 1
            try:
                record = enrich_solution(event, source)
                digest = record["sha256"]
                record["duplicateOf"] = seen_hashes.get(digest, {}).get("sourceUrl")
                if digest not in seen_hashes:
                    seen_hashes[digest] = record
                event_records.append(record)
            except Exception as exc:
                failures.append({
                    "eventUrl": event.get("eventUrl"),
                    "downloadName": source.get("downloadName"),
                    "sourceUrl": source.get("url"),
                    "error": f"{type(exc).__name__}: {exc}",
                })
            time.sleep(max(0.0, args.delay))
        records.append({
            "eventUrl": event.get("eventUrl"),
            "eventTitle": event.get("eventTitle"),
            "puzzleTitle": event.get("puzzleTitle"),
            "puzzle": event.get("puzzle"),
            "solutions": event_records,
        })
        if args.max_solutions > 0 and attempted >= args.max_solutions:
            break

    all_records = [s for e in records for s in e["solutions"]]
    complete_metrics = sum(1 for r in all_records if all(v is not None for v in r["metrics"].values()))
    trailing_clean = sum(1 for r in all_records if r["trailingBytes"] == 0)
    duplicate_count = sum(1 for r in all_records if r.get("duplicateOf"))
    puzzle_matches = sum(
        1 for r in all_records
        if r.get("puzzleFile") and any(
            r["puzzleFile"] in {Path((e.get("puzzle") or {}).get("file") or "").stem, (e.get("puzzle") or {}).get("file")}
            for e in records if e.get("eventUrl") == next((x.get("eventUrl") for x in records if r in x["solutions"]), None)
        )
    )

    result = {
        "schemaVersion": 1,
        "sourceCatalog": args.catalog.as_posix(),
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "publicSolutionsOnly": True,
            "binaryRetention": "none",
            "metadataCommitted": True,
            "identity": "sha256",
            "downloadDelaySeconds": args.delay,
        },
        "summary": {
            "selectedEvents": len(records),
            "attemptedSolutions": attempted,
            "parsedSolutions": len(all_records),
            "uniqueSolutionHashes": len(seen_hashes),
            "duplicateSolutionHashes": duplicate_count,
            "completeEmbeddedMetrics": complete_metrics,
            "zeroTrailingBytes": trailing_clean,
            "puzzleFileMatches": puzzle_matches,
            "failures": len(failures),
        },
        "events": records,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if all_records else 3


if __name__ == "__main__":
    raise SystemExit(main())
