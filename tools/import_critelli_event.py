from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote_to_bytes, urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "OpusMagnumCodexResearch/0.3 (+https://github.com/Fandalah-tech/opus-magnum-pattern-library)"
DEFAULT_EVENT = "https://events.critelli.technology/OM2026Weeklies1_LiquidPerfumes"
DEFAULT_SUBMISSIONS = "https://events.critelli.technology/submissions/19f7ad44e24b92dbe47c4b6536a35aa1"


@dataclass(frozen=True)
class Link:
    url: str
    text: str
    download_name: str | None = None


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[Link] = []
        self.forms: list[str] = []
        self.embedded_urls: list[str] = []
        self._href: str | None = None
        self._download: str | None = None
        self._text: list[str] = []

    @staticmethod
    def _resolve(base_url: str, value: str) -> str:
        # Critelli embeds puzzle binaries directly in the event page as
        # data:application/octet-stream;base64,... URLs. urljoin is intended for
        # hierarchical URLs, so preserve data URIs verbatim.
        if value.lower().startswith("data:"):
            return value
        return urljoin(base_url, value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for _, value in attrs:
            if value and (".puzzle" in value.lower() or ".solution" in value.lower()):
                self.embedded_urls.append(self._resolve(self.base_url, value))
        if tag == "a" and values.get("href"):
            self._href = self._resolve(self.base_url, values["href"] or "")
            self._download = values.get("download")
            self._text = []
        elif tag == "form" and values.get("action"):
            self.forms.append(self._resolve(self.base_url, values["action"] or ""))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append(Link(self._href, text, self._download))
            self._href = None
            self._download = None
            self._text = []


def decode_data_uri(url: str) -> tuple[bytes, str]:
    if not url.lower().startswith("data:"):
        raise ValueError("not a data URI")
    header, sep, payload = url.partition(",")
    if not sep:
        raise ValueError("malformed data URI")
    metadata = header[5:]
    parts = metadata.split(";") if metadata else []
    content_type = parts[0] or "text/plain"
    is_base64 = any(part.lower() == "base64" for part in parts[1:])
    try:
        data = base64.b64decode(payload, validate=True) if is_base64 else unquote_to_bytes(payload)
    except Exception as exc:
        raise ValueError(f"invalid data URI payload: {exc}") from exc
    return data, content_type


def fetch(url: str, timeout: int = 30) -> tuple[bytes, str]:
    if url.lower().startswith("data:"):
        return decode_data_uri(url)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def parse_links(html: bytes, base_url: str) -> tuple[list[Link], list[str], list[str]]:
    parser = LinkParser(base_url)
    text = html.decode("utf-8", errors="replace")
    parser.feed(text)
    embedded = list(parser.embedded_urls)
    for match in re.finditer(r"(?:https?://[^\s\"'<>]+|[A-Za-z0-9_./-]+\.(?:puzzle|solution))(?:\?[^\s\"'<>]*)?", text, re.I):
        embedded.append(urljoin(base_url, match.group(0)))
    return parser.links, parser.forms, embedded


def same_origin(url: str, origin: str) -> bool:
    # Inline data URIs are part of the already-fetched trusted event document;
    # no additional origin is contacted when they are decoded.
    if url.lower().startswith("data:"):
        return True
    return urlparse(url).netloc == urlparse(origin).netloc


def looks_like_file(link: Link, suffix: str) -> bool:
    path = "" if link.url.lower().startswith("data:") else urlparse(link.url).path.lower()
    haystack = f"{path} {link.text.lower()} {(link.download_name or '').lower()}"
    return suffix in haystack


def discover_file_links(links: Iterable[Link], embedded_urls: Iterable[str], suffix: str, origin: str) -> list[Link]:
    found: dict[str, Link] = {}
    for link in links:
        if same_origin(link.url, origin) and looks_like_file(link, suffix):
            # A data URI can be very large. Its hash is a compact stable key for
            # discovery deduplication while preserving the actual Link object.
            key = hashlib.sha256(link.url.encode("utf-8")).hexdigest() if link.url.lower().startswith("data:") else link.url
            found.setdefault(key, link)
    for url in embedded_urls:
        if url.lower().startswith("data:"):
            continue  # data URIs need the anchor's download= filename to classify them
        candidate = Link(url=url, text=Path(urlparse(url).path).name)
        if same_origin(url, origin) and looks_like_file(candidate, suffix):
            found.setdefault(url, candidate)
    return list(found.values())


def safe_name(link: Link, suffix: str, digest: str) -> str:
    url_name = "" if link.url.lower().startswith("data:") else Path(urlparse(link.url).path).name
    candidates = [link.download_name, url_name, link.text]
    for candidate in candidates:
        if candidate and suffix in candidate.lower():
            cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-.")
            if cleaned:
                return cleaned
    return f"{digest}{suffix}"


def public_source_url(link: Link) -> str:
    # Never copy an inline puzzle binary into the public provenance report.
    return "inline-data-uri" if link.url.lower().startswith("data:") else link.url


def write_binary(root: Path, category: str, link: Link, data: bytes, suffix: str) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    folder = root / category
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_name(link, suffix, digest)
    path = folder / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        path = folder / f"{path.stem}-{digest[:12]}{path.suffix or suffix}"
    path.write_bytes(data)
    return {
        "url": public_source_url(link),
        "downloadName": link.download_name,
        "path": path.as_posix(),
        "sha256": digest,
        "bytes": len(data),
    }


def download_candidates(links: Iterable[Link], root: Path, category: str, suffix: str, delay: float) -> tuple[list[dict], list[dict]]:
    downloaded: list[dict] = []
    failures: list[dict] = []
    seen_hashes: set[str] = set()
    for link in links:
        try:
            data, content_type = fetch(link.url)
            if content_type == "text/html" or not data:
                raise ValueError(f"unexpected content type {content_type!r}")
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            item = write_binary(root, category, link, data, suffix)
            item["contentType"] = content_type
            downloaded.append(item)
        except Exception as exc:
            failures.append({"url": public_source_url(link), "error": f"{type(exc).__name__}: {exc}"})
        if not link.url.lower().startswith("data:"):
            time.sleep(max(0.0, delay))
    return downloaded, failures


def public_link(link: Link) -> dict:
    value = asdict(link)
    value["url"] = public_source_url(link)
    value["inline"] = link.url.lower().startswith("data:")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one public Critelli event and its public submissions with provenance.")
    parser.add_argument("--event-url", default=DEFAULT_EVENT)
    parser.add_argument("--submissions-url", default=DEFAULT_SUBMISSIONS)
    parser.add_argument("--dataset-root", type=Path, default=Path(".datasets/critelli-events/liquid-perfumes"))
    parser.add_argument("--report", type=Path, default=Path("reports/critelli-liquid-perfumes-import.json"))
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--max-solutions", type=int, default=0, help="0 downloads all discovered solution links.")
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()

    event_html, event_type = fetch(args.event_url)
    event_links, event_forms, event_embedded = parse_links(event_html, args.event_url)
    puzzle_links = discover_file_links(event_links, event_embedded, ".puzzle", args.event_url)

    time.sleep(max(0.0, args.delay))
    submissions_html, submissions_type = fetch(args.submissions_url)
    submission_links, submission_forms, submission_embedded = parse_links(submissions_html, args.submissions_url)
    solution_links = discover_file_links(submission_links, submission_embedded, ".solution", args.submissions_url)
    if args.max_solutions > 0:
        solution_links = solution_links[: args.max_solutions]

    report: dict = {
        "schemaVersion": 3,
        "source": "events.critelli.technology",
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "event": {
            "url": args.event_url,
            "contentType": event_type,
            "forms": event_forms,
            "puzzleLinks": [public_link(link) for link in puzzle_links],
        },
        "submissions": {
            "url": args.submissions_url,
            "contentType": submissions_type,
            "forms": submission_forms,
            "solutionLinks": [public_link(link) for link in solution_links],
        },
        "downloaded": {"puzzles": [], "solutions": []},
        "failures": {"puzzles": [], "solutions": []},
        "policy": {
            "sameOriginOnly": True,
            "inlinePuzzleDataSupported": True,
            "inlinePuzzlePayloadOmittedFromPublicReport": True,
            "userAgent": USER_AGENT,
            "rawFilesStoredUnderIgnoredDatasetDirectory": True,
            "publicReportContainsProvenanceAndHashesOnly": True,
        },
    }

    if not args.discover_only:
        puzzles, puzzle_failures = download_candidates(puzzle_links, args.dataset_root, "puzzles", ".puzzle", args.delay)
        solutions, solution_failures = download_candidates(solution_links, args.dataset_root, "solutions", ".solution", args.delay)
        report["downloaded"]["puzzles"] = puzzles
        report["downloaded"]["solutions"] = solutions
        report["failures"]["puzzles"] = puzzle_failures
        report["failures"]["solutions"] = solution_failures

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "puzzleLinks": len(puzzle_links),
        "solutionLinks": len(solution_links),
        "downloadedPuzzles": len(report["downloaded"]["puzzles"]),
        "downloadedSolutions": len(report["downloaded"]["solutions"]),
        "puzzleFailures": len(report["failures"]["puzzles"]),
        "solutionFailures": len(report["failures"]["solutions"]),
        "report": args.report.as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["downloaded"]["puzzles"] and report["downloaded"]["solutions"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
