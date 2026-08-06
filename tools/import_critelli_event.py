from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "OpusMagnumCodexResearch/0.1 (+https://github.com/Fandalah-tech/opus-magnum-pattern-library)"
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
        self._href: str | None = None
        self._download: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self._href = urljoin(self.base_url, values["href"] or "")
            self._download = values.get("download")
            self._text = []
        elif tag == "form" and values.get("action"):
            self.forms.append(urljoin(self.base_url, values["action"] or ""))

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


def fetch(url: str, timeout: int = 30) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def parse_links(html: bytes, base_url: str) -> tuple[list[Link], list[str]]:
    parser = LinkParser(base_url)
    parser.feed(html.decode("utf-8", errors="replace"))
    return parser.links, parser.forms


def same_origin(url: str, origin: str) -> bool:
    return urlparse(url).netloc == urlparse(origin).netloc


def looks_like_file(link: Link, suffix: str) -> bool:
    path = urlparse(link.url).path.lower()
    haystack = f"{path} {link.text.lower()} {(link.download_name or '').lower()}"
    return suffix in haystack


def discover_file_links(links: Iterable[Link], suffix: str, origin: str) -> list[Link]:
    found: dict[str, Link] = {}
    for link in links:
        if same_origin(link.url, origin) and looks_like_file(link, suffix):
            found.setdefault(link.url, link)
    return list(found.values())


def safe_name(link: Link, suffix: str, digest: str) -> str:
    candidates = [link.download_name, Path(urlparse(link.url).path).name, link.text]
    for candidate in candidates:
        if candidate and suffix in candidate.lower():
            cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip("-.")
            if cleaned:
                return cleaned
    return f"{digest}{suffix}"


def write_binary(root: Path, category: str, link: Link, data: bytes, suffix: str) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    folder = root / category
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_name(link, suffix, digest)
    path = folder / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        path = folder / f"{path.stem}-{digest[:12]}{path.suffix or suffix}"
    path.write_bytes(data)
    return {"url": link.url, "path": path.as_posix(), "sha256": digest, "bytes": len(data)}


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
    event_links, event_forms = parse_links(event_html, args.event_url)
    puzzle_links = discover_file_links(event_links, ".puzzle", args.event_url)

    time.sleep(max(0.0, args.delay))
    submissions_html, submissions_type = fetch(args.submissions_url)
    submission_links, submission_forms = parse_links(submissions_html, args.submissions_url)
    solution_links = discover_file_links(submission_links, ".solution", args.submissions_url)
    if args.max_solutions > 0:
        solution_links = solution_links[: args.max_solutions]

    report: dict = {
        "schemaVersion": 1,
        "source": "events.critelli.technology",
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "event": {
            "url": args.event_url,
            "contentType": event_type,
            "forms": event_forms,
            "puzzleLinks": [asdict(link) for link in puzzle_links],
        },
        "submissions": {
            "url": args.submissions_url,
            "contentType": submissions_type,
            "forms": submission_forms,
            "solutionLinks": [asdict(link) for link in solution_links],
        },
        "downloaded": {"puzzles": [], "solutions": []},
        "policy": {
            "sameOriginOnly": True,
            "userAgent": USER_AGENT,
            "rawFilesStoredUnderIgnoredDatasetDirectory": True,
            "publicReportContainsProvenanceAndHashesOnly": True,
        },
    }

    if not args.discover_only:
        for link in puzzle_links:
            data, _ = fetch(link.url)
            report["downloaded"]["puzzles"].append(write_binary(args.dataset_root, "puzzles", link, data, ".puzzle"))
            time.sleep(max(0.0, args.delay))
        for link in solution_links:
            data, _ = fetch(link.url)
            report["downloaded"]["solutions"].append(write_binary(args.dataset_root, "solutions", link, data, ".solution"))
            time.sleep(max(0.0, args.delay))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "puzzleLinks": len(puzzle_links),
        "solutionLinks": len(solution_links),
        "downloadedPuzzles": len(report["downloaded"]["puzzles"]),
        "downloadedSolutions": len(report["downloaded"]["solutions"]),
        "report": args.report.as_posix(),
    }, ensure_ascii=False))
    return 0 if puzzle_links else 3


if __name__ == "__main__":
    raise SystemExit(main())
