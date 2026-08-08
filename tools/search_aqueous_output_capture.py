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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="fixtures/weeklies2026/aqueous-dagger-16c-reference.solution.b64")
    parser.add_argument("--out", default="reports/aqueous-output-search")
    parser.add_argument("--radius", type=int, default=4)
    args = parser.parse_args()

    reference = load_reference(Path(args.fixture))
    output_index = next(i for i, p in enumerate(reference["parts"]) if p.get("type") == "out-std")
    original = reference["parts"][output_index]
    oq, or_ = map(int, original.get("position") or (0, 0))

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    serial = 0

    # Search all product orientations and a generous local disk around the existing output.
    # This is intentionally cheap: output placement does not alter arm kinematics, so it can
    # reveal an earlier transient product pose that the original 16c solve simply did not capture.
    for dq, dr in hex_disk(args.radius):
        for rotation in range(6):
            if dq == 0 and dr == 0 and rotation == int(original.get("rotation") or 0):
                continue
            candidate = copy.deepcopy(reference)
            candidate["metrics"] = {}
            candidate["unknownMetrics"] = []
            candidate["name"] = "Codex Aqueous output capture search"
            out = candidate["parts"][output_index]
            out["position"] = [oq + dq, or_ + dr]
            out["rotation"] = rotation
            name = f"variant-{serial:04d}.solution"
            (root / name).write_bytes(write_solution_bytes(candidate))
            manifest.append({
                "file": name,
                "kind": "output-placement",
                "position": out["position"],
                "rotation": rotation,
                "delta": [dq, dr],
            })
            serial += 1

    (root / "manifest.json").write_text(json.dumps({
        "referenceMetrics": reference.get("metrics"),
        "outputPartIndex": output_index,
        "originalPosition": [oq, or_],
        "originalRotation": int(original.get("rotation") or 0),
        "candidateCount": serial,
        "variants": manifest,
    }, indent=2))
    print(f"generated {serial} output-placement variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
