from __future__ import annotations

import argparse
import base64
import copy
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import product
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.validate_aqueous_offsets import validate

CYCLE_RE = re.compile(r"cycle\s+(\d+)", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validator-url", required=True)
    ap.add_argument("--puzzle", required=True)
    ap.add_argument("--minus", required=True)
    ap.add_argument("--plus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    minus = parse_solution_bytes(Path(args.minus).read_bytes(), source_name="minus.solution")
    plus = parse_solution_bytes(Path(args.plus).read_bytes(), source_name="plus.solution")
    out = Path(args.out)
    cand_dir = out / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)

    # Stable part roles in both supplied boundary seeds.
    p_feed = 2
    p_main = 6
    p_salt = 7
    glyph_variable = 8

    # Explore exactly the small structural boundary between the -1 and +1 salt
    # seeds, with one-cell local glyph neighbors and one-cycle timing margins.
    glyph_positions = {
        tuple(minus["parts"][glyph_variable]["position"]),
        tuple(plus["parts"][glyph_variable]["position"]),
    }
    for q, r in list(glyph_positions):
        for dq, dr in ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)):
            glyph_positions.add((q + dq, r + dr))

    feed_starts = range(1, 5)       # supplied seeds use 2 and 3
    main_pivots = ("pivot_ccw", "pivot_cw")
    main_retract = (False, True)
    salt_starts = range(4, 8)       # supplied seeds use 5 and 6

    candidates: list[tuple[Path, dict]] = []
    serial = 0
    for feed_start, pivot, use_retract, salt_start, glyph_pos in product(
        feed_starts, main_pivots, main_retract, salt_starts, sorted(glyph_positions)
    ):
        c = copy.deepcopy(minus)
        c["metrics"] = {}
        c["unknownMetrics"] = []
        c["name"] = f"salt-boundary-{serial:05d}"

        c["parts"][p_feed]["program"] = [
            {"cycle": feed_start + 0, "instruction": "grab"},
            {"cycle": feed_start + 1, "instruction": "extend"},
            {"cycle": feed_start + 2, "instruction": "pivot_cw"},
            {"cycle": feed_start + 3, "instruction": "reset"},
        ]

        main = [
            {"cycle": 0, "instruction": "grab"},
            {"cycle": 1, "instruction": "rotate_ccw"},
            {"cycle": 2, "instruction": "extend"},
            {"cycle": 3, "instruction": pivot},
        ]
        if use_retract:
            main += [
                {"cycle": 4, "instruction": "retract"},
                {"cycle": 5, "instruction": "reset"},
            ]
        else:
            main += [{"cycle": 4, "instruction": "reset"}]
        c["parts"][p_main]["program"] = main

        c["parts"][p_salt]["program"] = [
            {"cycle": salt_start + 0, "instruction": "grab"},
            {"cycle": salt_start + 1, "instruction": "retract"},
            {"cycle": salt_start + 2, "instruction": "retract"},
            {"cycle": salt_start + 3, "instruction": "reset"},
        ]
        c["parts"][glyph_variable]["position"] = list(glyph_pos)

        path = cand_dir / f"candidate-{serial:05d}.solution"
        path.write_bytes(write_solution_bytes(c))
        candidates.append((path, {
            "feedStart": feed_start,
            "mainPivot": pivot,
            "mainRetract": use_retract,
            "saltStart": salt_start,
            "glyph": list(glyph_pos),
        }))
        serial += 1

    results = []
    issue_counts = Counter()
    closest = []
    with ThreadPoolExecutor(max_workers=max(1, min(8, args.workers))) as pool:
        future_map = {pool.submit(validate, args.validator_url, Path(args.puzzle), p): (p, meta) for p, meta in candidates}
        done = 0
        for fut in as_completed(future_map):
            p, meta = future_map[fut]
            done += 1
            try:
                v = fut.result()
            except Exception as exc:
                v = {"valid": False, "rawOutput": str(exc), "issues": [{"message": str(exc)}]}
            if v.get("valid"):
                record = {"file": p.name, "meta": meta, "metrics": v.get("metrics") or {}}
                results.append(record)
                if not (out / "best.solution").exists():
                    (out / "best.solution").write_bytes(p.read_bytes())
            else:
                raw = str(v.get("rawOutput") or "")
                issues = v.get("issues") or []
                sig = str((issues[0] if issues else {}).get("message") or raw or "unknown")
                sig = re.sub(r"cycle\s+\d+", "cycle N", sig, flags=re.I)
                issue_counts[sig[:220]] += 1
                m = CYCLE_RE.search(raw)
                cycle = int(m.group(1)) if m else -1
                closest.append({"cycle": cycle, "file": p.name, "meta": meta, "rawOutput": raw[:400]})
            if done % 100 == 0 or done == len(candidates):
                print(f"PROGRESS {done}/{len(candidates)} valid={len(results)}", flush=True)

    results.sort(key=lambda x: (
        int((x.get("metrics") or {}).get("cycles") or 10**9),
        int((x.get("metrics") or {}).get("area") or 10**9),
        int((x.get("metrics") or {}).get("cost") or 10**9),
    ))
    closest.sort(key=lambda x: (-x["cycle"], x["file"]))
    payload = {
        "candidateCount": len(candidates),
        "validCount": len(results),
        "results": results[:20],
        "closestInvalid": closest[:20],
        "issueCounts": issue_counts.most_common(20),
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"candidateCount": len(candidates), "validCount": len(results), "best": results[:3], "closest": closest[:3]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
