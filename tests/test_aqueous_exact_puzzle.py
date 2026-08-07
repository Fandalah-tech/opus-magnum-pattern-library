from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_solver.fragment_planner import analyze_two_fragment_assembly


def _exact_puzzle() -> dict:
    return {
        "name": "AQUEOUS DAGGER",
        "availableParts": {
            "rawFlags": 0x07C0170F,
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["equilibrium", "bonder", "unbonder", "multibonder", "calcification"],
        },
        "reagents": [
            {
                "id": "reagent-0",
                "atoms": [
                    {"id": "a0", "element": "water", "position": [-1, 0]},
                    {"id": "a1", "element": "water", "position": [-1, 1]},
                    {"id": "a2", "element": "water", "position": [0, 0]},
                ],
                "bonds": [
                    {"type": "normal", "from": [-1, 0], "to": [0, 0]},
                    {"type": "normal", "from": [-1, 1], "to": [0, 0]},
                    {"type": "normal", "from": [-1, 0], "to": [-1, 1]},
                ],
            },
            {
                "id": "reagent-1",
                "atoms": [
                    {"id": "a0", "element": "water", "position": [0, 0]},
                    {"id": "a1", "element": "water", "position": [-1, 0]},
                    {"id": "a2", "element": "water", "position": [-1, 1]},
                ],
                "bonds": [
                    {"type": "normal", "from": [-1, 0], "to": [0, 0]},
                    {"type": "normal", "from": [-1, 1], "to": [0, 0]},
                    {"type": "normal", "from": [-1, 0], "to": [-1, 1]},
                ],
            },
        ],
        "products": [
            {
                "id": "product-0",
                "atoms": [
                    {"id": "a0", "element": "water", "position": [0, 0]},
                    {"id": "a1", "element": "water", "position": [0, 1]},
                    {"id": "a2", "element": "water", "position": [1, 0]},
                    {"id": "a3", "element": "salt", "position": [0, -1]},
                    {"id": "a4", "element": "salt", "position": [-1, -1]},
                    {"id": "a5", "element": "salt", "position": [-1, 0]},
                ],
                "bonds": [
                    {"type": "normal", "from": [0, 1], "to": [1, 0]},
                    {"type": "normal", "from": [0, 0], "to": [1, 0]},
                    {"type": "normal", "from": [0, 0], "to": [0, 1]},
                    {"type": "normal", "from": [-1, -1], "to": [0, -1]},
                    {"type": "normal", "from": [-1, 0], "to": [0, -1]},
                    {"type": "normal", "from": [-1, -1], "to": [-1, 0]},
                    {"type": "normal", "from": [-1, 0], "to": [0, 0]},
                    {"type": "normal", "from": [0, -1], "to": [0, 0]},
                ],
            }
        ],
        "outputScale": 1,
        "production": False,
    }


def _program(entries):
    return [{"cycle": cycle, "instruction": instruction} for cycle, instruction in entries]


def _part(part_id, part_type, position, *, rotation=0, length=1, which=0, program=None):
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


def _candidate() -> dict:
    return {
        "parts": [
            _part("out", "out-std", (1, -1), rotation=1, which=0),
            _part("a-salt-arm", "arm1", (-2, 0), rotation=4, length=2,
                  program=_program([(0, "grab"), (1, "rotate_ccw"), (2, "rotate_ccw"),
                                    (3, "drop"), (4, "rotate_cw"), (5, "rotate_cw")])),
            _part("b-water-arm", "arm1", (2, -2), rotation=0,
                  program=_program([(0, "grab"), (3, "rotate_ccw"), (4, "drop"), (5, "rotate_cw")])),
            _part("z-pivot-arm", "arm1", (2, 0), rotation=3,
                  program=_program([(4, "grab"), (5, "pivot_ccw")])),
            # Same world-space source triangles as the reconstructed fixture,
            # but using the official reagent-local coordinates/orientations.
            _part("salt-input", "input", (-2, -2), rotation=3, which=0),
            _part("water-input", "input", (3, -2), rotation=4, which=1),
            _part("calc-0", "glyph-calcification", (0, -2)),
            _part("calc-1", "glyph-calcification", (1, -2)),
            _part("calc-2", "glyph-calcification", (0, -1)),
            _part("bond", "bonder", (0, 0), rotation=0),
        ]
    }


def test_exact_official_geometry_proves_n_six_and_bound_fifteen_for_l_two() -> None:
    plan = analyze_two_fragment_assembly(_exact_puzzle())
    assert plan.supported is True
    assert plan.input_bound_n(target_products=6) == 6
    assert plan.classical_cycle_bound(latency=2, target_products=6) == 15
    assert len(plan.cross_bonds) == 2


def test_existing_pipeline_runs_on_exact_official_geometry() -> None:
    puzzle = _exact_puzzle()
    solution = _candidate()
    timeline = build_program_timeline(solution, max_cycles=37)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(timeline)

    assert replay["summary"]["terminatedWithError"] is False
    assert simulator.delivered_products == {"out": 6}
