from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_parser.solution import parse_solution_bytes

REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def main() -> None:
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    parts = []
    for part in solution.get("parts", []):
        parts.append({
            "id": part.get("id"),
            "type": part.get("type"),
            "position": part.get("position"),
            "rotation": part.get("rotation"),
            "length": part.get("length"),
            "which": part.get("which"),
            "trackHexes": part.get("trackHexes"),
            "program": part.get("program"),
        })
    print(json.dumps({
        "name": solution.get("name"),
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "parts": parts,
    }, indent=2))


if __name__ == "__main__":
    main()
