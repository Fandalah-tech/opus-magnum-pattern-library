from __future__ import annotations

import argparse
import base64
import copy
import json
from itertools import combinations, product
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes

DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
ROTATABLE_TYPES = {"input", "out-std", "bonder", "bonder-speed"}
MOVABLE_TYPES = ROTATABLE_TYPES | {"glyph-calcification"}


def load_reference(path: Path) -> dict:
    raw = base64.b64decode(path.read_text().strip())
    return parse_solution_bytes(raw, source_name="aqueous-structural-parent.solution")


def clean(solution: dict, name: str) -> dict:
    candidate = copy.deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    candidate["name"] = name
    return candidate


def legal_program(program: list[dict]) -> bool:
    cycles = [int(item.get("cycle", 0)) for item in program]
    return min(cycles, default=0) >= 0 and len(cycles) == len(set(cycles))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ref = load_reference(Path(args.fixture))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    variants: list[tuple[dict, dict]] = []
    seen: set[bytes] = set()

    arm_indices = [i for i, part in enumerate(ref.get("parts") or []) if part.get("type") in ARM_TYPES]
    movable_indices = [i for i, part in enumerate(ref.get("parts") or []) if part.get("type") in MOVABLE_TYPES]

    def add(candidate: dict | None, meta: dict) -> None:
        if candidate is None:
            return
        payload = write_solution_bytes(candidate)
        if payload in seen:
            return
        seen.add(payload)
        variants.append((candidate, meta))

    # 1) Timing neighborhood in both directions.  Earlier-only search can get
    # trapped because a small delay can remove a collision and permit a later
    # compression elsewhere.
    timing_moves: list[tuple[int, int, int]] = []
    for pi in arm_indices:
        program = ref["parts"][pi].get("program") or []
        for ii, item in enumerate(program):
            for delta in (-1, 1):
                candidate = clean(ref, f"timing p{pi} i{ii} {delta:+d}")
                candidate["parts"][pi]["program"][ii]["cycle"] += delta
                if legal_program(candidate["parts"][pi]["program"]):
                    timing_moves.append((pi, ii, delta))
                    add(candidate, {"kind": "instruction-shift", "part": pi, "instruction": ii, "delta": delta})

        for start in range(len(program)):
            for delta in (-1, 1):
                candidate = clean(ref, f"suffix p{pi} s{start} {delta:+d}")
                for item in candidate["parts"][pi]["program"][start:]:
                    item["cycle"] += delta
                if legal_program(candidate["parts"][pi]["program"]):
                    add(candidate, {"kind": "suffix-shift", "part": pi, "start": start, "delta": delta})

        for delta in (-1, 1):
            candidate = clean(ref, f"phase p{pi} {delta:+d}")
            for item in candidate["parts"][pi]["program"]:
                item["cycle"] += delta
            if legal_program(candidate["parts"][pi]["program"]):
                add(candidate, {"kind": "program-phase", "part": pi, "delta": delta})

    # Coordinated phase changes let the search cross timing states that would
    # be invalid if either arm were shifted in isolation.
    for a, b in combinations(arm_indices, 2):
        for da, db in product((-1, 1), repeat=2):
            candidate = clean(ref, "paired arm phase")
            for item in candidate["parts"][a].get("program") or []:
                item["cycle"] += da
            for item in candidate["parts"][b].get("program") or []:
                item["cycle"] += db
            if legal_program(candidate["parts"][a].get("program") or []) and legal_program(candidate["parts"][b].get("program") or []):
                add(candidate, {"kind": "paired-phase", "parts": [a, b], "deltas": [da, db]})

    # 2) Rotate/pivot substitutions.  Keep this local but allow either timing
    # direction on the same arm.
    replacement = {
        "rotate_cw": "pivot_cw",
        "rotate_ccw": "pivot_ccw",
        "pivot_cw": "rotate_cw",
        "pivot_ccw": "rotate_ccw",
    }
    substitutions: list[tuple[int, int, str, str]] = []
    for pi in arm_indices:
        for ii, item in enumerate(ref["parts"][pi].get("program") or []):
            old = str(item.get("instruction") or "")
            if old not in replacement:
                continue
            new = replacement[old]
            substitutions.append((pi, ii, old, new))
            candidate = clean(ref, f"{old}->{new}")
            candidate["parts"][pi]["program"][ii]["instruction"] = new
            add(candidate, {"kind": "rotate-pivot", "part": pi, "instruction": ii, "from": old, "to": new})

    for pi, ii, old, new in substitutions:
        for tpi, tii, delta in timing_moves:
            if tpi != pi:
                continue
            candidate = clean(ref, "timing plus pivot")
            candidate["parts"][pi]["program"][ii]["instruction"] = new
            candidate["parts"][pi]["program"][tii]["cycle"] += delta
            if legal_program(candidate["parts"][pi].get("program") or []):
                add(candidate, {
                    "kind": "timing-plus-pivot", "part": pi, "action": ii,
                    "timing": tii, "delta": delta,
                })

    # 3) Arm geometry.  The previous search never moved an arm base or changed
    # its length.  Explore one local geometric step, plus coupled base/rotation
    # and base/length steps so the graph can cross otherwise-invalid states.
    for pi in arm_indices:
        part = ref["parts"][pi]
        q, r = part.get("position") or (0, 0)
        rotation = int(part.get("rotation") or 0) % 6
        length = int(part.get("length") or 1)
        length_options = [value for value in (length - 1, length + 1) if 1 <= value <= 3]

        for drot in (-1, 1):
            candidate = clean(ref, f"arm rotate p{pi}")
            candidate["parts"][pi]["rotation"] = (rotation + drot) % 6
            add(candidate, {"kind": "arm-base-rotate", "part": pi, "delta": drot})

        for new_length in length_options:
            candidate = clean(ref, f"arm length p{pi}")
            candidate["parts"][pi]["length"] = new_length
            add(candidate, {"kind": "arm-length", "part": pi, "length": new_length})

        for dq, dr in DIRECTIONS:
            new_position = [q + dq, r + dr]
            candidate = clean(ref, f"arm move p{pi}")
            candidate["parts"][pi]["position"] = new_position
            add(candidate, {"kind": "arm-base-move", "part": pi, "position": new_position})

            for drot in (-1, 1):
                candidate = clean(ref, f"arm move rotate p{pi}")
                candidate["parts"][pi]["position"] = new_position
                candidate["parts"][pi]["rotation"] = (rotation + drot) % 6
                add(candidate, {
                    "kind": "arm-move-rotate", "part": pi,
                    "position": new_position, "rotation": (rotation + drot) % 6,
                })

            for new_length in length_options:
                candidate = clean(ref, f"arm move length p{pi}")
                candidate["parts"][pi]["position"] = new_position
                candidate["parts"][pi]["length"] = new_length
                add(candidate, {
                    "kind": "arm-move-length", "part": pi,
                    "position": new_position, "length": new_length,
                })

    # 4) Puzzle-piece geometry.  Include reagent and calcification glyphs, which
    # were completely absent from the previous neighborhood.
    for pi in movable_indices:
        part = ref["parts"][pi]
        ptype = str(part.get("type") or "")
        q, r = part.get("position") or (0, 0)
        rotation = int(part.get("rotation") or 0) % 6

        if ptype in ROTATABLE_TYPES:
            for drot in (-1, 1):
                candidate = clean(ref, f"piece rotate p{pi}")
                candidate["parts"][pi]["rotation"] = (rotation + drot) % 6
                add(candidate, {"kind": "piece-rotate", "part": pi, "type": ptype, "delta": drot})

        for dq, dr in DIRECTIONS:
            new_position = [q + dq, r + dr]
            candidate = clean(ref, f"piece move p{pi}")
            candidate["parts"][pi]["position"] = new_position
            add(candidate, {"kind": "piece-move", "part": pi, "type": ptype, "position": new_position})

            if ptype in ROTATABLE_TYPES:
                for drot in (-1, 1):
                    candidate = clean(ref, f"piece move rotate p{pi}")
                    candidate["parts"][pi]["position"] = new_position
                    candidate["parts"][pi]["rotation"] = (rotation + drot) % 6
                    add(candidate, {
                        "kind": "piece-move-rotate", "part": pi, "type": ptype,
                        "position": new_position, "rotation": (rotation + drot) % 6,
                    })

    # 5) Bonder topology.  Add a locally adjacent bonder or remove one.  The
    # mechanical identity layer canonicalizes opposite endpoint encodings.
    bonders = [(i, p) for i, p in enumerate(ref["parts"]) if p.get("type") in {"bonder", "bonder-speed"}]
    for _, anchor in bonders:
        q, r = anchor.get("position") or (0, 0)
        for dq, dr in DIRECTIONS:
            for rot in range(6):
                candidate = clean(ref, "add adjacent bonder")
                candidate["parts"].append({
                    "type": "bonder", "enabled": True,
                    "position": [q + dq, r + dr], "length": 1,
                    "rotation": rot, "which": 0, "armNumber": 0, "program": [],
                })
                add(candidate, {"kind": "add-adjacent-bonder", "position": [q + dq, r + dr], "rotation": rot})

    if len(bonders) > 1:
        for pi, _ in reversed(bonders):
            candidate = clean(ref, f"remove bonder p{pi}")
            del candidate["parts"][pi]
            add(candidate, {"kind": "remove-bonder", "part": pi})

    manifest = []
    for number, (candidate, meta) in enumerate(variants):
        filename = f"variant-{number:05d}.solution"
        (out / filename).write_bytes(write_solution_bytes(candidate))
        manifest.append({"file": filename, **meta})

    payload = {
        "candidateCount": len(manifest),
        "armIndices": arm_indices,
        "movableIndices": movable_indices,
        "variants": manifest,
    }
    (out / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("candidateCount", "armIndices", "movableIndices")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
