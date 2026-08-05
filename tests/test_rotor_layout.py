from packages.opus_solver.rotor_layout import build_wide_rotor_layout, layout_solution_parts


def test_wide_rotor_layout_has_all_required_stations_and_seven_buffers() -> None:
    layout = build_wide_rotor_layout()

    assert layout.supported is True
    assert {station.kind for station in layout.stations} >= {
        "input", "unbonder", "baron", "bonder", "out-std",
    }
    assert len(layout.buffers) == 7


def test_wide_rotor_layout_compiles_to_solution_parts() -> None:
    layout = build_wide_rotor_layout()
    parts = layout_solution_parts(layout)

    assert len(parts) == len(layout.stations)
    assert len({part["id"] for part in parts}) == len(parts)
    assert all(part["program"] == [] for part in parts)
