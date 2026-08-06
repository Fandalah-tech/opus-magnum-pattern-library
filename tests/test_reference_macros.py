from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.opus_solver import compile_reference_macro, load_reference_macro


FIXTURE = Path("fixtures/macros/van-berlos-rotor-area44-confined-rotation.json")


def test_loads_a44_confined_rotation_as_atomic_macro() -> None:
    macro = load_reference_macro(FIXTURE)
    assert macro.name == "area44-confined-rotation"
    assert len(macro.actions) == 14
    assert {"rotor", "confined", "rotation", "plateau-crossing"} <= macro.tags
    assert macro.actions[0] == {
        "part-2": "rotate_cw",
        "part-9": "track_minus",
        "part-11": "retract",
    }
    assert macro.actions[-1] == {
        "part-2": "rotate_ccw",
        "part-9": "track_minus",
    }


def test_rejects_non_contiguous_reference_cycles() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["cycles"][1]["cycle"] += 1
    with pytest.raises(ValueError, match="contiguous"):
        compile_reference_macro(data)
