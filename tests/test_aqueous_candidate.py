from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_solution_bytes, write_solution_bytes


def _triangle(element: str) -> dict:
    return {
        "atoms": [
            {"id": "a0", "element": element, "position": [0, 0]},
            {"id": "a1", "element": element, "position": [-1, 1]},
            {"id": "a2", "element": element, "position": [0, 1]},
        ],
        "bonds": [
            {"type": "normal", "from": [0, 0], "to": [-1, 1]},
            {"type": "normal", "from": [0, 0], "to": [0, 1]},
            {"type": "normal", "from": [-1, 1], "to": [0, 1]},
        ],
    }


def _puzzle() -> dict:
    reagent0 = _triangle("water")
    reagent1 = _triangle("water")
    return {
        "name": "AQUEOUS DAGGER RECONSTRUCTION",
        "availableParts": {
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [reagent0, reagent1],
        "products": [{
            "atoms": [
                {"id": "s0", "element": "salt", "position": [0, 0]},
                {"id": "s1", "element": "salt", "position": [-1, 1]},
                {"id": "s2", "element": "salt", "position": [0, 1]},
                {"id": "w0", "element": "water", "position": [1, 0]},
                {"id": "w1", "element": "water", "position": [2, -1]},
                {"id": "w2", "element": "water", "position": [2, 0]},
            ],
            "bonds": [
                {"type": "normal", "from": [0, 0], "to": [-1, 1]},
                {"type": "normal", "from": [0, 0], "to": [0, 1]},
                {"type": "normal", "from": [-1, 1], "to": [0, 1]},
                {"type": "normal", "from": [1, 0], "to": [2, -1]},
                {"type": "normal", "from": [1, 0], "to": [2, 0]},
                {"type": "normal", "from": [2, -1], "to": [2, 0]},
                {"type": "normal", "from": [0, 0], "to": [1, 0]},
                {"type": "normal", "from": [0, 1], "to": [1, 0]},
            ],
        }],
        "outputScale": 1,
        "production": False,
    }


def _program(entries: list[tuple[int, str]]) -> list[dict]:
    return [{"cycle": cycle, "instruction": instruction} for cycle, instruction in entries]


def _part(
    part_id: str,
    part_type: str,
    position,
    *,
    rotation=0,
    length=1,
    which=0,
    program=None,
) -> dict:
    return {
        "id": part_id,
        "type": part_type,
        "enabled": True,
        "position": list(position),
        "rotation": rotation,
        "length": length,
        "which": which,
        "armNumber": 0,
        "program": list(program or []),
    }


def _solution() -> dict:
    return {
        "schemaVersion": "0.2.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/two-fragment-probe-v1"},
        "puzzleFile": "weeklies2026_aqueous-dagger",
        "name": "Codex Aqueous Dagger probe - 6-cycle pipeline",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [
            _part("out", "out-std", (1, -1), rotation=1, which=0),
            _part(
                "a-salt-arm", "arm1", (-2, 0), rotation=4, length=2,
                program=_program([
                    (0, "grab"), (1, "rotate_ccw"), (2, "rotate_ccw"),
                    (3, "drop"), (4, "rotate_cw"), (5, "rotate_cw"),
                ]),
            ),
            _part(
                "b-water-arm", "arm1", (2, -2), rotation=0, length=1,
                program=_program([
                    (0, "grab"), (3, "rotate_ccw"), (4, "drop"),
                    (5, "rotate_cw"),
                ]),
            ),
            _part(
                "z-pivot-arm", "arm1", (2, 0), rotation=3, length=1,
                program=_program([(4, "grab"), (5, "pivot_ccw"), (6, "drop")]),
            ),
            _part("salt-input", "input", (-2, -2), rotation=4, which=0),
            _part("water-input", "input", (3, -2), rotation=5, which=1),
            _part("calc-0", "glyph-calcification", (0, -2)),
            _part("calc-1", "glyph-calcification", (1, -2)),
            _part("calc-2", "glyph-calcification", (0, -1)),
            _part("bond", "bonder", (0, 0), rotation=0),
        ],
        "trailingBytes": 0,
    }


PERIOD = [
    {"a-salt-arm": "grab", "b-water-arm": "grab"},
    {"a-salt-arm": "rotate_ccw"},
    {"a-salt-arm": "rotate_ccw"},
    {"a-salt-arm": "drop", "b-water-arm": "rotate_ccw"},
    {"a-salt-arm": "rotate_cw", "b-water-arm": "drop", "z-pivot-arm": "grab"},
    {"a-salt-arm": "rotate_cw", "b-water-arm": "rotate_cw", "z-pivot-arm": "pivot_ccw"},
    {"z-pivot-arm": "drop"},
]


def test_single_bonder_candidate_delivers_six_products_without_pipeline_overlap() -> None:
    simulator = Simulator.from_models(_puzzle(), _solution())
    for _ in range(6):
        for instructions in PERIOD:
            simulator.step(instructions)

    assert simulator.delivered_products == {"out": 6}
    assert simulator.world.cycle == 42


def test_serialized_tapes_pipeline_at_six_cycles_and_deliver_six() -> None:
    encoded = write_solution_bytes(_solution())
    parsed = parse_solution_bytes(encoded, source_name="aqueous-probe.solution")
    timeline = build_program_timeline(parsed, max_cycles=37)
    simulator = Simulator.from_models(_puzzle(), parsed)
    replay = simulator.run_timeline(timeline)

    assert timeline["summary"]["globalPeriod"] == 6
    assert replay["summary"]["terminatedWithError"] is False
    assert simulator.delivered_products == {"part-0": 6}
    assert parsed["puzzleFile"] == "weeklies2026_aqueous-dagger"
