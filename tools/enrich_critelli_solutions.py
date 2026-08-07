from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from packages.opus_parser.solution import parse_solution_bytes
from tools.import_critelli_event import fetch


def choose_events(catalog: dict, event_url: str | None) -> list[dict]:
    events = [e for e in catalog.get("events", []) if (e.get("submissions") or {}).get("solutions")]
    if event_url:
        events = [e for e in events if e.get("eventUrl") == event_url]
    return events


def derive_filename_metadata(download_name: str | None, solution_name: str | None) -> dict:
    value = str(download_name or "")
    stem = value[:-9] if value.lower().endswith(".solution") else value
    submitter = None
    sequence = None
    confidence = "none"

    # Critelli filenames observed in public submissions are normally:
    # PUZZLE_<opaque numeric sequence>_<solution name>_<submitter>.solution
    # Use the parsed internal solution name as an anchor where possible, then
    # fall back to the final underscore only. This remains derived metadata.
    if solution_name:
        marker = f"_{solution_name}_"
        index = stem.rfind(marker)
        if index >= 0:
            submitter = stem[index + len(marker):].strip() or None
            confidence = "high" if submitter else "none"
    if submitter is None and "_" in stem:
        submitter = stem.rsplit("_", 1)[-1].strip() or None
        confidence = "medium" if submitter else "none"

    match = re.search(r"_(\d{12,})_", stem)
    if match:
        sequence = match.group(1)
    return {
        "submitter": submitter,
        "submitterSource": "download-filename" if submitter else None,
        "submitterConfidence": confidence,
        "filenameSequence": sequence,
    }


def submission_id(source_url: str) -> str | None:
    values = parse_qs(urlparse(source_url).query).get("submission") or []
    return values[0] if values else None


def enrich_solution(event: dict, source: dict) -> dict:
    data, content_type = fetch(source["url"])
    parsed = parse_solution_bytes(data, source_name=source.get("downloadName"))
    puzzle_file = (event.get("puzzle") or {}).get("file")
    derived = derive_filename_metadata(source.get("downloadName"), parsed["name"])
    return {
        "downloadName": source.get("downloadName"),
        "sourceUrl": source["url"],
        "submissionId": submission_id(source["url"]),
        **derived,
        "contentType": content_type,
        "sha256": parsed["source"]["sha256"],
        "bytes": parsed["source"]["size"],
        "formatVersion": parsed["format"]["version"],
        "puzzleFile": parsed["puzzleFile"],
        "eventPuzzleFile": puzzle_file,
        "solutionName": parsed["name"],
        "metrics": parsed["metrics"],
        "partCount": len(parsed["parts"]),
        "trailingBytes": parsed["trailingBytes"],
        "eventPuzzleSha256": (event.get("puzzle") or {}).get("sha256"),
    }


def failure_signature(error: str) -> str:
    text = re.sub(r"https?://\S+", "<url>", error)
    text = re.sub(r"submission=[0-9a-f]+", "submission=<id>", text, flags=re.I)
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<hash>", text, flags=re.I)
    return text[:240]


def metric_gap(record: dict) -> str:
    missing = [key for key, value in (record.get("metrics") or {}).items() if value is None]
    return ",".join(missing) if missing else "complete"


def puzzle_matches(record: dict) -> bool:
    actual = record.get("puzzleFile")
    expected = record.get("eventPuzzleFile")
    if not actual or not expected:
        return False
    return actual in {expected, Path(expected).stem}


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
                    "submissionId": submission_id(source.get("url") or ""),
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
    complete_metrics = sum(1 for r in all_records if metric_gap(r) == "complete")
    trailing_clean = sum(1 for r in all_records if r["trailingBytes"] == 0)
    duplicate_count = sum(1 for r in all_records if r.get("duplicateOf"))
    match_count = sum(1 for r in all_records if puzzle_matches(r))
    submitter_count = sum(1 for r in all_records if r.get("submitter"))
    failure_counts = Counter(failure_signature(f["error"]) for f in failures)
    gap_counts = Counter(metric_gap(r) for r in all_records)
    version_counts = Counter(str(r.get("formatVersion")) for r in all_records)

    result = {
        "schemaVersion": 3,
        "sourceCatalog": args.catalog.as_posix(),
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "publicSolutionsOnly": True,
            "binaryRetention": "none",
            "metadataCommitted": True,
            "identity": "sha256",
            "downloadDelaySeconds": args.delay,
            "submitterMetadata": "derived-from-public-download-filename",
        },
        "summary": {
            "selectedEvents": len(records),
            "attemptedSolutions": attempted,
            "parsedSolutions": len(all_records),
            "uniqueSolutionHashes": len(seen_hashes),
            "duplicateSolutionHashes": duplicate_count,
            "completeEmbeddedMetrics": complete_metrics,
            "zeroTrailingBytes": trailing_clean,
            "puzzleFileMatches": match_count,
            "solutionsWithDerivedSubmitter": submitter_count,
            "failures": len(failures),
            "formatVersions": dict(sorted(version_counts.items())),
            "metricCoverage": dict(sorted(gap_counts.items())),
            "failureSignatures": [
                {"error": signature, "count": count}
                for signature, count in failure_counts.most_common(12)
            ],
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
