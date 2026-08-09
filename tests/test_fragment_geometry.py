from packages.opus_analysis.fragments import extract_solution_fragments


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
