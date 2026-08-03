#!/usr/bin/env python3
"""Submit matching .puzzle/.solution pairs to the deployed validator."""
from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path


def encode_multipart(puzzle: Path, solution: Path) -> tuple[bytes, str]:
    boundary = "----opus-codex-validation-boundary"
    chunks: list[bytes] = []
    for field, path in (("puzzle", puzzle), ("solution", solution)):
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    puzzles = {p.stem: p for p in root.rglob("*.puzzle")}
    solutions = {p.stem: p for p in root.rglob("*.solution")}
    return [(puzzles[key], solutions[key]) for key in sorted(puzzles.keys() & solutions.keys())]


def validate(url: str, puzzle: Path, solution: Path, timeout: int) -> dict:
    body, boundary = encode_multipart(puzzle, solution)
    request = urllib.request.Request(
        url.rstrip("/") + "/validate",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"valid": False, "httpStatus": exc.code, "error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:  # noqa: BLE001 - report network failures in benchmark output
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=75)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pairs = find_pairs(args.root)[: max(args.limit, 0)]
    results = []
    for puzzle, solution in pairs:
        result = validate(args.url, puzzle, solution, args.timeout)
        results.append({
            "puzzle": puzzle.relative_to(args.root).as_posix(),
            "solution": solution.relative_to(args.root).as_posix(),
            "result": result,
        })
        print(f"{puzzle.name}: {'valid' if result.get('valid') else 'invalid/error'}")

    report = {
        "schemaVersion": "0.1.0",
        "validatorUrl": args.url,
        "pairCount": len(pairs),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Validated {len(pairs)} matching pair(s)")
    return 0 if pairs else 2


if __name__ == "__main__":
    raise SystemExit(main())
