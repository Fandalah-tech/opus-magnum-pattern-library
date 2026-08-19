from packages.opus_analysis.canonical import canonical_solution_hash, rotate_hex
from packages.opus_analysis.fragments import extract_solution_fragments
from packages.opus_solver.layout import transplant_geometry


def _solution(offset=0):
    return {
        "puzzleFile": "P.puzzle",
        "parts": [
            {"id": "in", "type": "input", "position": [offset, 0], "rotation": 0, "length": 1, "which": 0, "program": []},
            {"id": "arm", "type": "arm1", "position": [offset + 1, 0], "rotation": 3, "length": 1, "which": 0, "armNumber": 1, "program": [{"cycle": 7, "instruction": "grab"}, {"cycle": 8, "instruction": "rotate_cw"}]},
        ],
    }


def test_fragment_contains_canonical_geometry_payload():
    fragment = next(item for item in extract_solution_fragments(_solution()) if item["role"] == "feed")
    geometry = fragment["geometry"]
    assert geometry["coordinateSystem"] == "canonical-axial-relative"
    assert geometry["partCount"] == 2
    assert len(geometry["parts"]) == 2
    cycles = sorted(instruction["cycle"] for part in geometry["parts"] for instruction in part.get("program", []))
    assert cycles == [0, 1]


def test_translated_fragment_has_identical_mechanism_geometry():
    left = next(item for item in extract_solution_fragments(_solution(0)) if item["role"] == "feed")
    right = next(item for item in extract_solution_fragments(_solution(10)) if item["role"] == "feed")
    assert left["canonicalMechanismHash"] == right["canonicalMechanismHash"]
    assert left["geometry"] == right["geometry"]


def test_track_offsets_rotate_but_are_never_translated_as_world_cells():
    geometry = {
        "anchorPartType": "input",
        "parts": [
            {"type": "input", "position": [0, 0], "rotation": 0, "program": []},
            {"type": "track", "position": [1, 0], "rotation": 0, "trackHexes": [[0, 0], [1, 0]], "program": []},
        ],
    }
    parts = transplant_geometry(geometry, anchor_position=(10, 5), anchor_rotation=1, instance_id="x")
    track = next(part for part in parts if part["type"] == "track")
    assert track["position"] == [10, 6]
    assert track["trackHexes"] == [[0, 0], [0, 1]]


def test_canonical_track_hash_is_translation_and_rotation_invariant():
    base = {
        "puzzleFile": "P",
        "parts": [
            {"type": "track", "position": [3, -2], "rotation": 0, "trackHexes": [[0, 0], [1, 0]], "program": []},
            {"type": "piston", "position": [3, -2], "rotation": 2, "length": 2, "program": [{"cycle": 4, "instruction": "grab"}]},
        ],
    }
    rotated = {
        "puzzleFile": "P",
        "parts": [
            {
                **part,
                "position": list(rotate_hex(tuple(part["position"]), 1)),
                "rotation": (int(part.get("rotation") or 0) + 1) % 6,
                **(
                    {"trackHexes": [list(rotate_hex(tuple(cell), 1)) for cell in part.get("trackHexes", [])]}
                    if part["type"] == "track" else {}
                ),
            }
            for part in base["parts"]
        ],
    }
    assert canonical_solution_hash(base, normalize_time=True) == canonical_solution_hash(rotated, normalize_time=True)
