from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.opus_solver import compile_reference_macro, load_reference_macro


FIXTURE = Path("fixtures/macros/van-berlos-rotor-area44-confined-rotation.json")


def _arm(*, origin, rotation, length, track_index, grabbing, held_branches):
    return SimpleNamespace(
        origin=origin,
        rotation=rotation,
        length=length,
        track_index=track_index,
        grabbing=grabbing,
        held_atoms={branch: f"atom-{branch}" for branch in held_branches},
    )


def _compatible_simulator():
    return SimpleNamespace(arms={
        "part-11": _arm(
            origin=(2, -1), rotation=5, length=3, track_index=0,
            grabbing=True, held_branches=[],
        ),
        "part-2": _arm(
            origin=(0, 3), rotation=1, length=1, track_index=0,
            grabbing=True, held_branches=[0, 1, 2, 3, 4, 5],
        ),
        "part-9": _arm(
            origin=(4, -6), rotation=0, length=2, track_index=4,
            grabbing=False, held_branches=[],
        ),
    })


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


def test_a44_macro_guard_requires_reference_arm_configuration() -> None:
    macro = load_reference_macro(FIXTURE)
    simulator = _compatible_simulator()
    assert macro.applicable(simulator)

    simulator.arms["part-2"].rotation = 0
    assert not macro.applicable(simulator)


def test_a44_macro_guard_requires_all_six_baron_branches_held() -> None:
    macro = load_reference_macro(FIXTURE)
    simulator = _compatible_simulator()
    simulator.arms["part-2"].held_atoms.pop(5)
    assert not macro.applicable(simulator)


def test_rejects_non_contiguous_reference_cycles() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["cycles"][1]["cycle"] += 1
    with pytest.raises(ValueError, match="contiguous"):
        compile_reference_macro(data)
