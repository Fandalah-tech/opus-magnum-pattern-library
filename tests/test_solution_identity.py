from __future__ import annotations

import base64
from pathlib import Path

from packages.opus_parser import parse_solution_bytes, write_solution_bytes
from tools.solution_identity import mechanical_id, translation_class_id


def _seed(tmp_path: Path) -> tuple[dict, Path]:
    raw = base64.b64decode(Path("fixtures/weeklies2026/aqueous-dagger-27c-single-reference.solution.b64").read_text().strip())
    model = parse_solution_bytes(raw, source_name="seed.solution")
    p = tmp_path / "seed.solution"
    p.write_bytes(raw)
    return model, p


def _write(tmp_path: Path, name: str, model: dict) -> Path:
    p = tmp_path / name
    model = dict(model)
    model["metrics"] = {}
    model["unknownMetrics"] = []
    p.write_bytes(write_solution_bytes(model))
    return p


def test_mechanical_identity_ignores_part_order_arm_number_and_name(tmp_path: Path) -> None:
    model, seed = _seed(tmp_path)
    changed = dict(model)
    changed["name"] = "completely different display name"
    changed["parts"] = [dict(p) for p in reversed(model["parts"])]
    for i, part in enumerate(changed["parts"]):
        part["armNumber"] = 900 + i
    variant = _write(tmp_path, "reordered.solution", changed)
    assert mechanical_id(seed) == mechanical_id(variant)


def test_translation_class_groups_uniform_shift_but_mechanical_identity_does_not(tmp_path: Path) -> None:
    model, seed = _seed(tmp_path)
    shifted = dict(model)
    shifted["parts"] = []
    for original in model["parts"]:
        part = dict(original)
        q, r = part.get("position") or (0, 0)
        part["position"] = [int(q) + 7, int(r) - 4]
        if part.get("type") == "track":
            part["trackHexes"] = [[int(q) + 7, int(r) - 4] for q, r in (part.get("trackHexes") or [])]
        shifted["parts"].append(part)
    variant = _write(tmp_path, "shifted.solution", shifted)
    assert mechanical_id(seed) != mechanical_id(variant)
    assert translation_class_id(seed) == translation_class_id(variant)


def test_real_geometry_change_changes_both_identities(tmp_path: Path) -> None:
    model, seed = _seed(tmp_path)
    changed = dict(model)
    changed["parts"] = [dict(p) for p in model["parts"]]
    target = next(p for p in changed["parts"] if str(p.get("type", "")).startswith("arm"))
    target["rotation"] = (int(target.get("rotation") or 0) + 1) % 6
    variant = _write(tmp_path, "rotated-arm.solution", changed)
    assert mechanical_id(seed) != mechanical_id(variant)
    assert translation_class_id(seed) != translation_class_id(variant)
