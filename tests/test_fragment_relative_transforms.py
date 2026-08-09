from packages.opus_analysis.canonical import rotate_hex
from packages.opus_analysis.convergence import extract_convergence_motifs
from packages.opus_analysis.fragment_flow import _relative_transform


def _part(position, rotation):
    return {"position": list(position), "rotation": rotation}


def test_relative_transform_is_invariant_to_global_rotation():
    source = _part((0, 0), 0)
    target = _part((2, -1), 2)
    expected = _relative_transform(source, target)

    source_rotated = _part(rotate_hex((0, 0), 1), 1)
    target_rotated = _part(rotate_hex((2, -1), 1), 3)
    assert _relative_transform(source_rotated, target_rotated) == expected


def test_relative_transform_reports_rotation_delta():
    transform = _relative_transform(_part((5, 5), 4), _part((6, 5), 1))
    assert transform["frame"] == "source-anchor-local"
    assert transform["rotationDelta"] == 3


def test_convergence_motif_preserves_input_transform_evidence():
    transform_a = {"frame": "source-anchor-local", "delta": [1, 0], "rotationDelta": 0}
    transform_b = {"frame": "source-anchor-local", "delta": [-1, 1], "rotationDelta": 2}
    graph = {
        "nodes": [
            {"anchorPartId": "a", "role": "feed", "canonicalMechanismHash": "fa"},
            {"anchorPartId": "b", "role": "feed", "canonicalMechanismHash": "fb"},
            {"anchorPartId": "c", "role": "bonding", "canonicalMechanismHash": "bond"},
        ],
        "edges": [
            {"sourceAnchorPartId": "a", "targetAnchorPartId": "c", "relation": "bond-created", "relativeTransform": transform_a, "observationCount": 1, "firstCycle": 1, "lastCycle": 1},
            {"sourceAnchorPartId": "b", "targetAnchorPartId": "c", "relation": "bond-created", "relativeTransform": transform_b, "observationCount": 1, "firstCycle": 1, "lastCycle": 1},
        ],
    }
    motif = extract_convergence_motifs(graph)[0]
    transforms = [item["relativeTransforms"][0] for item in motif["inputs"]]
    assert transform_a in transforms
    assert transform_b in transforms
