from __future__ import annotations

import argparse
import base64
import copy
import json
import shutil
import subprocess
from itertools import combinations
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.search_aqueous_structural import DIRECTIONS, ARM_TYPES, STATION_TYPES, MOTION_ACTIONS, legal_program

MAX_EXTRA = 6000


def clean(solution: dict, name: str) -> dict:
    candidate = copy.deepcopy(solution)
    candidate["metrics"] = {}
    candidate["unknownMetrics"] = []
    candidate["name"] = name
    return candidate


def move(candidate: dict, index: int, direction: tuple[int, int]) -> None:
    q, r = candidate["parts"][index].get("position") or (0, 0)
    candidate["parts"][index]["position"] = [int(q) + direction[0], int(r) + direction[1]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    fixture = Path(args.fixture)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base_out = out / "_base"
    shutil.rmtree(base_out, ignore_errors=True)
    base_out.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["python", "tools/search_aqueous_structural.py", "--fixture", str(fixture), "--out", str(base_out)],
        check=True,
    )
    base_manifest = json.loads((base_out / "manifest.json").read_text())

    ref = parse_solution_bytes(base64.b64decode(fixture.read_text().strip()), source_name="aqueous-v9-parent.solution")
    parts = ref.get("parts") or []
    arms = [i for i, p in enumerate(parts) if p.get("type") in ARM_TYPES]
    stations = [i for i, p in enumerate(parts) if p.get("type") in STATION_TYPES]
    compression_stations = [i for i in stations if parts[i].get("type") in {"input", "out-std", "bonder", "bonder-speed"}]

    manifest: list[dict] = []
    seen: set[bytes] = set()
    serial = 0

    def emit(candidate: dict, meta: dict) -> None:
        nonlocal serial
        if len(manifest) >= len(base_manifest.get("variants", [])) + MAX_EXTRA:
            return
        payload = write_solution_bytes(candidate)
        if payload in seen:
            return
        seen.add(payload)
        filename = f"variant-{serial:06d}.solution"
        serial += 1
        (out / filename).write_bytes(payload)
        manifest.append({"file": filename, **meta})

    # Preserve the full v8 neighborhood first.
    for meta in base_manifest.get("variants", []):
        src = base_out / meta["file"]
        payload = src.read_bytes()
        if payload in seen:
            continue
        seen.add(payload)
        filename = f"variant-{serial:06d}.solution"
        serial += 1
        (out / filename).write_bytes(payload)
        manifest.append({"file": filename, **{k: v for k, v in meta.items() if k != "file"}})

    timed: list[tuple[int, int, int]] = []
    for ai in arms:
        for ii, item in enumerate(parts[ai].get("program") or []):
            timed.append((ai, ii, int(item.get("cycle") or 0)))
    late = sorted(timed, key=lambda x: (-x[2], x[0], x[1]))[:18]

    # O. Triple one-cycle compression. Pairwise timing moves cannot cross states
    # where three dependent instructions must advance together.
    for triple in combinations(late, 3):
        candidate = clean(ref, "triple timing compression")
        touched = set()
        for ai, ii, _ in triple:
            candidate["parts"][ai]["program"][ii]["cycle"] -= 1
            touched.add(ai)
        if all(legal_program(candidate["parts"][ai].get("program") or []) for ai in touched):
            emit(candidate, {"kind": "triple-timing-compress", "items": [[a, i] for a, i, _ in triple]})

    # P. Compress two arm suffixes together. This targets a C27 -> C26 pipeline
    # change rather than isolated instruction timing.
    for a, b in combinations(arms, 2):
        pa = parts[a].get("program") or []
        pb = parts[b].get("program") or []
        for sa in range(1, len(pa)):
            for sb in range(1, len(pb)):
                candidate = clean(ref, "paired suffix compression")
                for item in candidate["parts"][a]["program"][sa:]:
                    item["cycle"] = int(item.get("cycle") or 0) - 1
                for item in candidate["parts"][b]["program"][sb:]:
                    item["cycle"] = int(item.get("cycle") or 0) - 1
                if legal_program(candidate["parts"][a].get("program") or []) and legal_program(candidate["parts"][b].get("program") or []):
                    emit(candidate, {"kind": "paired-suffix-compress", "arms": [a, b], "starts": [sa, sb]})

    # Q. Cross the common invalid intermediate: move/rotate/resize an arm while
    # simultaneously pulling its remaining tape one cycle earlier.
    for ai in arms:
        program = parts[ai].get("program") or []
        base_rot = int(parts[ai].get("rotation") or 0) % 6
        base_len = int(parts[ai].get("length") or 1)
        for start in range(1, len(program)):
            for d in DIRECTIONS:
                for drot in (-1, 1):
                    candidate = clean(ref, "arm geometry suffix compression")
                    move(candidate, ai, d)
                    candidate["parts"][ai]["rotation"] = (base_rot + drot) % 6
                    for item in candidate["parts"][ai]["program"][start:]:
                        item["cycle"] = int(item.get("cycle") or 0) - 1
                    if legal_program(candidate["parts"][ai].get("program") or []):
                        emit(candidate, {"kind": "arm-move-rotate-compress", "part": ai, "start": start, "delta": list(d), "rotationDelta": drot})
                for length in (1, 2, 3):
                    if length == base_len:
                        continue
                    candidate = clean(ref, "arm move length suffix compression")
                    move(candidate, ai, d)
                    candidate["parts"][ai]["length"] = length
                    for item in candidate["parts"][ai]["program"][start:]:
                        item["cycle"] = int(item.get("cycle") or 0) - 1
                    if legal_program(candidate["parts"][ai].get("program") or []):
                        emit(candidate, {"kind": "arm-move-length-compress", "part": ai, "start": start, "delta": list(d), "length": length})

    # R. A station move can remove the collision introduced by a one-cycle tape
    # compression. Explore this directly instead of requiring a valid intermediate.
    for ai in arms:
        program = parts[ai].get("program") or []
        starts = list(range(max(1, len(program) - 4), len(program)))
        for start in starts:
            for si in compression_stations:
                for d in DIRECTIONS:
                    candidate = clean(ref, "station plus suffix compression")
                    move(candidate, si, d)
                    for item in candidate["parts"][ai]["program"][start:]:
                        item["cycle"] = int(item.get("cycle") or 0) - 1
                    if legal_program(candidate["parts"][ai].get("program") or []):
                        emit(candidate, {"kind": "station-suffix-compress", "part": ai, "station": si, "start": start, "delta": list(d)})

    # S. Introduce a short round-trip track while compressing the tail. This is a
    # topology jump that cannot be reached through a sequence of valid no-track states.
    if not any(p.get("type") == "track" for p in parts):
        for ai in arms:
            q, r = map(int, parts[ai].get("position") or (0, 0))
            program = parts[ai].get("program") or []
            motion_slots = [ii for ii, item in enumerate(program) if str(item.get("instruction") or "") in MOTION_ACTIONS]
            for d in DIRECTIONS:
                nq, nr = q + d[0], r + d[1]
                track = {"type": "track", "enabled": True, "position": [q, r], "length": 1,
                         "rotation": 0, "which": 0, "program": [], "trackHexes": [[q, r], [nq, nr]], "armNumber": 0}
                for ia, ib in combinations(motion_slots, 2):
                    for start in range(max(1, len(program) - 3), len(program)):
                        candidate = clean(ref, "track roundtrip compressed tail")
                        candidate["parts"].append(copy.deepcopy(track))
                        candidate["parts"][ai]["program"][ia]["instruction"] = "track_plus"
                        candidate["parts"][ai]["program"][ib]["instruction"] = "track_minus"
                        for item in candidate["parts"][ai]["program"][start:]:
                            item["cycle"] = int(item.get("cycle") or 0) - 1
                        if legal_program(candidate["parts"][ai].get("program") or []):
                            emit(candidate, {"kind": "track-compressed-tail", "part": ai, "instructions": [ia, ib], "start": start, "delta": list(d)})

    shutil.rmtree(base_out, ignore_errors=True)
    payload = {"candidateCount": len(manifest), "armIndices": arms, "stationIndices": stations,
               "baseCandidates": len(base_manifest.get("variants", [])), "macroCandidates": max(0, len(manifest) - len(base_manifest.get("variants", []))),
               "variants": manifest}
    (out / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("candidateCount", "baseCandidates", "macroCandidates", "armIndices", "stationIndices")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
