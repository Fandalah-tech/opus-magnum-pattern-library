from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_solution, write_solution


def _position(value):
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _next_name(output_dir: Path, stem: str) -> Path:
    path = output_dir / f"{stem}.solution"
    index = 1
    while path.exists():
        path = output_dir / f"{stem}-{index}.solution"
        index += 1
    return path


def generate(solution_path: Path, output_dir: Path, *, collision_u: int, collision_v: int) -> dict:
    solution = parse_solution(solution_path)
    collision = (int(collision_u), int(collision_v))
    output_dir.mkdir(parents=True, exist_ok=True)

    matching = [
        part for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "arm1"
        and _position(part.get("position")) == collision
    ]
    variants = []

    for arm in matching:
        arm_id = str(arm.get("id") or "")
        length = max(1, int(arm.get("length") or 1))
        rotation = int(arm.get("rotation") or 0) % 6
        direction = DIRECTIONS[rotation]
        tip = (collision[0] + direction[0] * length, collision[1] + direction[1] * length)

        removed = deepcopy(solution)
        removed["parts"] = [
            part for part in removed.get("parts", []) or []
            if str(part.get("id") or "") != arm_id
        ]
        path = _next_name(output_dir, f"{arm_id}-removed")
        write_solution(removed, path)
        variants.append({
            "mode": "remove-collision-base-arm",
            "armPartId": arm_id,
            "oldBase": list(collision),
            "oldRotation": rotation,
            "preservedTip": list(tip),
            "solution": str(path),
        })

        for new_rotation in range(6):
            if new_rotation == rotation:
                continue
            new_direction = DIRECTIONS[new_rotation]
            new_base = (
                tip[0] - new_direction[0] * length,
                tip[1] - new_direction[1] * length,
            )
            if new_base == collision:
                continue
            relocated = deepcopy(solution)
            relocated_arm = next(
                part for part in relocated.get("parts", []) or []
                if str(part.get("id") or "") == arm_id
            )
            relocated_arm["position"] = [new_base[0], new_base[1]]
            relocated_arm["rotation"] = new_rotation
            path = _next_name(output_dir, f"{arm_id}-rotation-{new_rotation}")
            write_solution(relocated, path)
            variants.append({
                "mode": "relocate-collision-base-arm",
                "armPartId": arm_id,
                "oldBase": list(collision),
                "oldRotation": rotation,
                "newBase": list(new_base),
                "newRotation": new_rotation,
                "preservedTip": list(tip),
                "solution": str(path),
            })

    return {
        "schemaVersion": "0.1.0",
        "kind": "oracle-collision-base-repair-variants",
        "baselineSolution": solution_path.name,
        "collisionLocation": list(collision),
        "matchingArmCount": len(matching),
        "variantCount": len(variants),
        "targetSolutionBytesUsed": 0,
        "variants": variants,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate target-free arm-base repairs from an OMSim collision location.")
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--collision-u", type=int, required=True)
    parser.add_argument("--collision-v", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = generate(
        args.solution,
        args.output_dir,
        collision_u=args.collision_u,
        collision_v=args.collision_v,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("collisionLocation", "matchingArmCount", "variantCount", "targetSolutionBytesUsed")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
