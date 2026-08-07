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
        "name": "Codex Aqueous Dagger probe - 7-cycle period",
        "metrics": {},
        "unknownMetrics": [],
        "parts": [
            # After the second cross-bond, the complete molecule has been
            # pivoted +60 degrees around w0. This output matches that pose.
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
            # This arm's tip is fixed on the shared water atom (1, 0). It takes
            # over after the feed arms release and pivots the assembled molecule
            # so the same standard bonder can make the second cross-bond.
            _part(
                "z-pivot-arm", "arm1", (2, 0), rotation=3, length=1,
                program=_program([(4, "grab"), (5, "pivot_ccw"), (6, "drop")]),
            ),
            _part("salt-input", "input", (-2, -2), rotation=4, which=0),
            _part("water-input", "input", (3, -2), rotation=5, which=1),
            _part("calc-0", "glyph-calcification", (0, -2)),
            _part("calc-1", "glyph-calcification", (1, -2)),
            _part("calc-2", "glyph-calcification", (0, -1)),
            # One physical bonder only. In the initial assembly pose it creates
            # s0-w0. After pivot_ccw around w0, s2 occupies the same salt cell
            # and the glyph creates s2-w0.
            _part("bond", "bonder", (0, 0), rotation=0),
        ],
        "trailingBytes": 0,
    }


PERIOD = [
    {"a-salt-arm": "grab", "b-water-arm": "grab"},
    {"a-salt-arm": "rotate_ccw"},
    {"a-salt-arm": "rotate_ccw"},
    {"a-salt-arm": "drop", "b-water-arm": "rotate_ccw"},
    # Arm IDs deliberately sort in feed->pivot order, so b-water-arm drops
    # before z-pivot-arm grabs the shared atom in this same cycle.
    {"a-salt-arm": "rotate_cw", "b-water-arm": "drop", "z-pivot-arm": "grab"},
    {"a-salt-arm": "rotate_cw", "b-water-arm": "rotate_cw", "z-pivot-arm": "pivot_ccw"},
    {"z-pivot-arm": "drop"},
]


def test_single_bonder_candidate_delivers_six_products() -> None:
    simulator = Simulator.from_models(_puzzle(), _solution())
    for _ in range(6):
        for instructions in PERIOD:
            simulator.step(instructions)

    assert simulator.delivered_products == {"out": 6}
    assert simulator.world.cycle == 42


def test_candidate_round_trips_and_replays_from_real_program_tapes() -> None:
    encoded = write_solution_bytes(_solution())
    parsed = parse_solution_bytes(encoded, source_name="aqueous-probe.solution")
    timeline = build_program_timeline(parsed, max_cycles=42)
    simulator = Simulator.from_models(_puzzle(), parsed)
    replay = simulator.run_timeline(timeline)

    assert replay["summary"]["terminatedWithError"] is False
    assert simulator.delivered_products == {"out": 6}
    assert parsed["puzzleFile"] == "weeklies2026_aqueous-dagger"
