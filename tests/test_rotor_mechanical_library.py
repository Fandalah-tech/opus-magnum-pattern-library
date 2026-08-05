import json
from pathlib import Path

from packages.opus_solver.rotor_mechanical_library import (
    build_rotor_seed_macro_library,
    compile_program_window,
    learn_program_windows,
)


FIXTURE = Path("fixtures/solutions/van-berlos-rotor-area42-confined-seed.parsed.json")


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_compile_program_window_preserves_synchronized_cycles():
    macro = compile_program_window(_fixture(), "prefix", 9, 12, tags={"confined"})

    assert len(macro.actions) == 4
    assert macro.actions[0] == {"part-10": "pivot_cw", "part-12": "grab"}
    assert macro.actions[1] == {"part-10": "pivot_cw", "part-12": "retract"}
    assert macro.actions[2] == {"part-10": "track_plus", "part-12": "track_minus"}
    assert macro.actions[3] == {"part-10": "drop", "part-12": "rotate_cw"}


def test_program_window_learning_is_nonempty_and_deduplicated():
    macros = learn_program_windows(_fixture(), lengths=(2, 3))
    signatures = [tuple(tuple(sorted(frame.items())) for frame in macro.actions) for macro in macros]

    assert macros
    assert len(signatures) == len(set(signatures))
    assert all("learned" in macro.tags for macro in macros)


def test_rotor_library_contains_trusted_confined_reorientation():
    macros = build_rotor_seed_macro_library(_fixture())
    trusted = macros[0]

    assert trusted.name == "rotor-confined-reorientation-prefix"
    assert len(trusted.actions) == 13
    assert {"rotor", "rotation", "confined", "handoff", "trusted"} <= trusted.tags
