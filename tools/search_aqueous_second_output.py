from __future__ import annotations

import argparse
import base64
import copy
import json
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes


def load_reference(path: Path) -> dict:
    return parse_solution_bytes(
        base64.b64decode(path.read_text().strip()),
        source_name="aqueous-dagger-16c-reference.solution",
    )


def hex_disk(radius: int):
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= radius:
                yield q, r


def output_part(position, rotation: int, serial: int) -> dict:
    return {
        "id": f"search-output-{serial}",
        "type": "out-std",
        "enabled": True,
        "position": list(position),
        "rotation": rotation,
        "length": 1,
        "which": 0,
        "armNumber": 0,
        "program": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64")
    parser.add_argument("--out", default="reports/aqueous-second-output-search")
    parser.add_argument("--radius", type=int, default=3)
    args = parser.parse_args()

    reference = load_reference(Path(args.fixture))
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    serial = 0

    # The third right-side product is complete after the decisive pivot with its
    # held/root water at (4,-2). Search local output transforms around that pose.
    center = (4, -2)
    for dq, dr in hex_disk(args.radius):
        position = (center[0] + dq, center[1] + dr)
        for rotation in range(6):
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous duplicate output overlap"
            candidate["parts"].append(output_part(position, rotation, serial))
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name,
                "kind": "add-second-output",
                "position": list(position),
                "rotation": rotation,
            })
            serial += 1

    (root / "manifest.json").write_text(json.dumps({
        "referenceMetrics": reference.get("metrics"),
        "candidateCount": serial,
        "variants": manifest,
    }, indent=2))
    print(f"generated {serial} duplicate-output variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
