from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from tools.import_critelli_event import (
    Link,
    USER_AGENT,
    decode_data_uri,
    discover_file_links,
    discover_submissions_url,
    fetch,
    parse_links,
    public_source_url,
)

ROOT_URL = "https://events.critelli.technology/"


@dataclass(frozen=True)
class IndexedLink:
    url: str
    text: str


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.h1: list[str] = []
        self.h2: list[str] = []
        self._capture: str | None = None
        self._buf: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {"title", "h1", "h2"}:
            self._capture = tag
            self._buf = []

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            self.text.append(clean)
            if self._capture:
                self._buf.append(clean)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == tag:
            value = " ".join(self._buf).strip()
            if tag == "title":
                self.title = value or self.title
            elif tag == "h1" and value:
                self.h1.append(value)
            elif tag == "h2" and value:
                self.h2.append(value)
            self._capture = None
            self._buf = []


def normalize_text(html: bytes) -> TextCollector:
    parser = TextCollector()
    parser.feed(html.decode("utf-8", errors="replace"))
    return parser


def public_event_links(index_html: bytes, root_url: str) -> list[IndexedLink]:
    links, _, _ = parse_links(index_html, root_url)
    seen: set[str] = set()
    out: list[IndexedLink] = []
    root_host = urlparse(root_url).netloc
    for link in links:
        url = link.url
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != root_host:
            continue
        if url.rstrip("/") == root_url.rstrip("/") or "/submissions/" in parsed.path or "/download/" in parsed.path:
            continue
        if "." in Path(parsed.path).name:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(IndexedLink(url=url, text=link.text.strip()))
    return out


def find_inline_puzzle(links: list[Link]) -> Link | None:
    for link in links:
        if link.url.lower().startswith("data:") and (link.download_name or "").lower().endswith(".puzzle"):
            return link
    return None


def event_metadata(event_url: str, html: bytes) -> dict | None:
    links, forms, _ = parse_links(html, event_url)
    puzzle = find_inline_puzzle(links)
    if puzzle is None:
        return None

    raw, content_type = decode_data_uri(puzzle.url)
    digest = hashlib.sha256(raw).hexdigest()
    text = normalize_text(html)
    joined = "\n".join(text.text)

    title = text.h1[0] if text.h1 else text.title or puzzle.download_name or event_url.rsplit("/", 1)[-1]
    puzzle_title = text.h2[0] if text.h2 else None
    author = None
    match = re.search(r"^by\s+(.+)$", joined, re.I | re.M)
    if match:
        author = match.group(1).strip()

    ended = None
    match = re.search(r"event\s+(?:ended|ends)\s+on\s+([^\n]+)", joined, re.I)
    if match:
        ended = match.group(1).strip()

    metrics: list[str] = []
    if "METRICS" in text.text:
        start = text.text.index("METRICS") + 1
        for item in text.text[start: start + 12]:
            if item in {"REAGENTS", "PRODUCTS", "NOTES"}:
                break
            metrics.append(item)

    return {
        "eventUrl": event_url,
        "eventTitle": title,
        "puzzleTitle": puzzle_title,
        "author": author,
        "ended": ended,
        "submissionsUrl": discover_submissions_url(links, event_url),
        "puzzle": {
            "file": puzzle.download_name,
            "sha256": digest,
            "bytes": len(raw),
            "contentType": content_type,
            "source": "inline-data-uri",
        },
        "metricsText": metrics,
        "forms": forms,
    }


def inventory_submissions(url: str) -> dict:
    html, content_type = fetch(url)
    links, _, embedded = parse_links(html, url)
    solutions = discover_file_links(links, embedded, ".solution", url)
    records = []
    for link in solutions:
        records.append({
            "downloadName": link.download_name,
            "url": public_source_url(link),
        })
    return {
        "contentType": content_type,
        "count": len(records),
        "solutions": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Critelli Opus Magnum events and build a metadata-only inventory.")
    parser.add_argument("--root-url", default=ROOT_URL)
    parser.add_argument("--output", type=Path, default=Path("reports/critelli-event-catalog.json"))
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--max-pages", type=int, default=0, help="0 visits every same-origin index link.")
    parser.add_argument("--include-submissions", action="store_true", help="Visit public submissions pages and inventory solution links without downloading binaries.")
    args = parser.parse_args()

    index_html, _ = fetch(args.root_url)
    candidates = public_event_links(index_html, args.root_url)
    if args.max_pages > 0:
        candidates = candidates[: args.max_pages]

    events: list[dict] = []
    skipped: list[dict] = []
    failures: list[dict] = []
    for i, candidate in enumerate(candidates, start=1):
        try:
            html, content_type = fetch(candidate.url)
            if content_type != "text/html":
                skipped.append({"url": candidate.url, "reason": f"content-type:{content_type}"})
            else:
                metadata = event_metadata(candidate.url, html)
                if metadata:
                    metadata["indexText"] = candidate.text
                    if args.include_submissions and metadata.get("submissionsUrl"):
                        time.sleep(max(0.0, args.delay))
                        try:
                            metadata["submissions"] = inventory_submissions(metadata["submissionsUrl"])
                        except Exception as exc:
                            metadata["submissions"] = {"error": f"{type(exc).__name__}: {exc}", "count": None, "solutions": []}
                    events.append(metadata)
                else:
                    skipped.append({"url": candidate.url, "reason": "no-inline-puzzle"})
        except Exception as exc:
            failures.append({"url": candidate.url, "error": f"{type(exc).__name__}: {exc}"})
        if i < len(candidates):
            time.sleep(max(0.0, args.delay))

    by_hash: dict[str, dict] = {}
    duplicate_events: list[dict] = []
    for event in events:
        digest = event["puzzle"]["sha256"]
        if digest in by_hash:
            duplicate_events.append({"sha256": digest, "canonicalEvent": by_hash[digest]["eventUrl"], "duplicateEvent": event["eventUrl"]})
        else:
            by_hash[digest] = event

    report = {
        "schemaVersion": 2,
        "source": args.root_url,
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "userAgent": USER_AGENT,
        "policy": {
            "sameOriginOnly": True,
            "metadataOnly": True,
            "inlinePuzzlePayloadOmitted": True,
            "solutionBinariesDownloaded": False,
            "crawlDelaySeconds": args.delay,
        },
        "summary": {
            "indexCandidates": len(candidates),
            "puzzleEvents": len(events),
            "uniquePuzzles": len(by_hash),
            "duplicatePuzzleEvents": len(duplicate_events),
            "eventsWithPublicSubmissions": sum(1 for event in events if event.get("submissionsUrl")),
            "publicSolutionLinks": sum(int((event.get("submissions") or {}).get("count") or 0) for event in events),
            "skippedPages": len(skipped),
            "failures": len(failures),
        },
        "events": events,
        "duplicates": duplicate_events,
        "skipped": skipped,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if events else 3


if __name__ == "__main__":
    raise SystemExit(main())
