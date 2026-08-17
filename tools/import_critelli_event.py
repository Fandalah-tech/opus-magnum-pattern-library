from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

CRITELLI_BASE = "https://events.critelli.technology"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


class SubmissionTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"text": [], "links": []}
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href:
                self._cell["links"].append(href)

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = _clean_text(self._cell["text"])
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _metric(value: str, names: tuple[str, str, str]) -> dict[str, int] | None:
    parts = [part.strip() for part in value.split("/")]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return {name: int(part) for name, part in zip(names, parts)}


def parse_submission_page(html: str, *, page_url: str) -> list[dict[str, Any]]:
    parser = SubmissionTableParser()
    parser.feed(html)
    if not parser.rows:
        return []

    header_index = None
    headers: list[str] = []
    for index, row in enumerate(parser.rows):
        candidate = [str(cell["text"]).strip().lower().rstrip("?") for cell in row]
        if "submitter" in candidate and "solution name" in candidate and "download" in candidate:
            header_index = index
            headers = candidate
            break
    if header_index is None:
        return []

    records: list[dict[str, Any]] = []
    for source_rank, row in enumerate(parser.rows[header_index + 1 :], start=1):
        if len(row) < len(headers):
            continue
        cells = {headers[i]: row[i] for i in range(len(headers))}
        download_cell = cells.get("download", {"links": []})
        download_href = next((href for href in download_cell.get("links", []) if "/download/" in href), None)
        if not download_href:
            continue
        download_url = urllib.parse.urljoin(page_url, download_href)
        submission_id = urllib.parse.parse_qs(urllib.parse.urlparse(download_url).query).get("submission", [None])[0]
        notes_cell = cells.get("notes", {"text": "", "links": []})
        cga_raw = str(cells.get("cga", {}).get("text", ""))
        bca_raw = str(cells.get("bca", {}).get("text", ""))
        showcase_raw = str(cells.get("showcase", {}).get("text", ""))
        records.append({
            "sourceRank": source_rank,
            "submitter": str(cells.get("submitter", {}).get("text", "")),
            "pronouns": str(cells.get("pronouns", {}).get("text", "")),
            "solutionName": str(cells.get("solution name", {}).get("text", "")),
            "cga": _metric(cga_raw, ("cycles", "cost", "area")),
            "cgaRaw": cga_raw,
            "bca": _metric(bca_raw, ("boundingHexagon", "cycles", "area")),
            "bcaRaw": bca_raw,
            "submissionTimeUtc": str(cells.get("submission time (utc)", {}).get("text", "")),
            "showcase": showcase_raw.strip().lower() == "yes",
            "downloadUrl": download_url,
            "submissionId": submission_id,
            "notesText": str(notes_cell.get("text", "")),
            "notesUrls": [urllib.parse.urljoin(page_url, href) for href in notes_cell.get("links", [])],
        })
    return records


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "opus-magnum-pattern-library/1.0"})


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(_request(url), timeout=180) as response:
        return response.read()


def write_index(root: Path, *, event_id: str, page_url: str, puzzle_name: str | None, records: list[dict[str, Any]]) -> Path:
    index = {
        "schemaVersion": "0.1.0",
        "source": "critelli-events",
        "eventId": event_id,
        "sourcePage": page_url,
        "archiveUrl": f"{CRITELLI_BASE}/archive/{event_id}",
        "csvUrl": f"{CRITELLI_BASE}/csv/{event_id}",
        "puzzleName": puzzle_name,
        "submissionRecordCount": len(records),
        "solutionFileCount": sum(1 for item in records if item.get("file")),
        "downloadErrorCount": sum(1 for item in records if item.get("error")),
        "scoringSubmissionCount": sum(1 for item in records if not item.get("showcase")),
        "showcaseCount": sum(1 for item in records if item.get("showcase")),
        "uniqueSubmitterCount": len({str(item.get("submitter")) for item in records if item.get("submitter")}),
        "solutions": records,
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / "index.json"
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and inventory all solutions from one Critelli event submissions page.")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--root", type=Path, default=Path(".datasets/critelli-event"))
    parser.add_argument("--page-url")
    parser.add_argument("--puzzle-name")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    page_url = args.page_url or f"{CRITELLI_BASE}/submissions/{args.event_id}"
    args.root.mkdir(parents=True, exist_ok=True)
    raw_html_path = args.root / "submissions.html"
    if args.force or not raw_html_path.exists():
        raw_html_path.write_bytes(fetch_bytes(page_url))
    html = raw_html_path.read_text(encoding="utf-8")
    records = parse_submission_page(html, page_url=page_url)
    if args.limit is not None:
        records = records[: args.limit]
    if not records:
        raise RuntimeError(f"No Critelli submission rows found at {page_url}")

    files_root = args.root / "solutions"
    files_root.mkdir(parents=True, exist_ok=True)
    failures = 0
    for number, record in enumerate(records, start=1):
        submission_id = str(record.get("submissionId") or f"row-{number:04d}")
        destination = files_root / f"{number:04d}-{submission_id}.solution"
        try:
            if args.force or not destination.exists():
                temporary = destination.with_suffix(destination.suffix + ".part")
                temporary.unlink(missing_ok=True)
                temporary.write_bytes(fetch_bytes(str(record["downloadUrl"])))
                temporary.replace(destination)
            record.update({
                "file": destination.relative_to(args.root).as_posix(),
                "size": destination.stat().st_size,
                "sha256": sha256(destination),
                "puzzleName": args.puzzle_name,
            })
        except Exception as exc:
            failures += 1
            record["error"] = f"{type(exc).__name__}: {exc}"
        if number % 50 == 0 or number == len(records):
            write_index(args.root, event_id=args.event_id, page_url=page_url, puzzle_name=args.puzzle_name, records=records)
            print(json.dumps({"processed": number, "total": len(records), "downloadErrors": failures}), flush=True)

    index = write_index(args.root, event_id=args.event_id, page_url=page_url, puzzle_name=args.puzzle_name, records=records)
    print(json.dumps({
        "eventId": args.event_id,
        "submissions": len(records),
        "solutions": sum(1 for item in records if item.get("file")),
        "downloadErrors": failures,
        "uniqueSubmitters": len({str(item.get("submitter")) for item in records if item.get("submitter")}),
        "index": str(index),
    }, ensure_ascii=False), flush=True)
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
