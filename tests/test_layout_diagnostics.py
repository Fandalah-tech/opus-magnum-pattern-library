from packages.opus_solver.layout_diagnostics import analyze_layout_geometry, part_occupied_cells


def _part(part_id, part_type, position=(0, 0), rotation=0, length=1, program=None, **extra):
    return {
        "id": part_id,
        "type": part_type,
        "position": list(position),
        "rotation": rotation,
        "length": length,
        "program": list(program or []),
        **extra,
    }


def test_bonder_footprint_rotates_exactly():
    footprint = part_occupied_cells(_part("b", "bonder", (3, 4), rotation=1))
    assert footprint["precision"] == "exact"
    assert footprint["cells"] == {(3, 4), (3, 5)}


def test_known_piece_overlap_is_exact_static_conflict():
    parts = [
        _part("b", "bonder", (0, 0)),
        _part("c", "glyph-calcification", (1, 0)),
    ]
    result = analyze_layout_geometry(parts)
    assert result["summary"]["exactStaticConflictCount"] == 1
    assert result["staticConflicts"][0]["cells"] == [[1, 0]]


def test_arm_base_on_track_is_not_static_conflict():
    parts = [
        _part("track", "track", (0, 0), trackHexes=[[0, 0], [1, 0]]),
        _part("arm", "arm1", (0, 0)),
    ]
    result = analyze_layout_geometry(parts)
    assert result["summary"]["exactStaticConflictCount"] == 0


def test_track_cells_are_offsets_from_serialized_origin():
    footprint = part_occupied_cells(
        _part("track", "track", (7, -4), trackHexes=[[0, 0], [1, 0], [1, -1]])
    )
    assert footprint["cells"] == {(7, -4), (8, -4), (8, -5)}


def test_arm_workspace_overlap_is_risk_not_static_invalidity():
    parts = [
        _part("a", "arm1", (0, 0), length=1),
        _part("b", "arm1", (2, 0), length=1),
    ]
    result = analyze_layout_geometry(parts)
    assert result["summary"]["exactStaticConflictCount"] == 0
    assert result["summary"]["armWorkspaceOverlapCount"] == 1


def test_unknown_piece_overlap_is_marked_approximate():
    parts = [
        _part("u", "future-glyph", (0, 0)),
        _part("c", "glyph-calcification", (0, 0)),
    ]
    result = analyze_layout_geometry(parts)
    assert result["summary"]["approximateStaticConflictCount"] == 1
    assert result["staticConflicts"][0]["precision"] == "approximate"
