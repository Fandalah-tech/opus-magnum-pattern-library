from packages.opus_solver.layout import (
    apply_forward_transform,
    apply_inverse_transform,
    materialize_assembly_layout,
)


def _geometry(anchor_type):
    return {
        "coordinateSystem": "canonical-axial-relative",
        "timeNormalization": "global-min-instruction-cycle",
        "anchorPartType": anchor_type,
        "parts": [
            {"type": anchor_type, "position": [0, 0], "rotation": 0, "length": 1, "which": 0, "program": []},
        ],
    }


def _fragment(role, mechanism, anchor_type):
    return {"role": role, "canonicalMechanismHash": mechanism, "representativeGeometry": _geometry(anchor_type)}


def _edge(sr, sh, tr, th, relation, delta, rotation_delta=0):
    return {
        "sourceRole": sr,
        "sourceMechanismHash": sh,
        "targetRole": tr,
        "targetMechanismHash": th,
        "relation": relation,
        "relativeTransforms": {
            "preferred": {"frame": "source-anchor-local", "delta": list(delta), "rotationDelta": rotation_delta},
            "variantCount": 1,
            "variants": [],
        },
    }


def test_forward_and_inverse_transform_round_trip():
    transform = {"delta": [2, -1], "rotationDelta": 2}
    target_position, target_rotation = apply_forward_transform((4, 3), 5, transform)
    source_position, source_rotation = apply_inverse_transform(target_position, target_rotation, transform)
    assert source_position == (4, 3)
    assert source_rotation == 5


def test_materialize_two_branch_convergence_and_output():
    fragment_index = {
        "fragments": [
            _fragment("feed", "fa", "input"),
            _fragment("feed", "fb", "input"),
            _fragment("conversion", "calc", "glyph-calcification"),
            _fragment("bonding", "bond", "bonder"),
            _fragment("output", "out", "out-std"),
        ]
    }
    candidate = {
        "convergence": {
            "targetRole": "bonding",
            "targetMechanismHash": "bond",
            "inputs": [
                {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relations": ["bond-created"]},
                {"sourceRole": "feed", "sourceMechanismHash": "fb", "relations": ["bond-created"]},
            ],
            "samples": [
                {
                    "inputs": [
                        {"sourceRole": "conversion", "sourceMechanismHash": "calc", "relativeTransforms": [{"delta": [1, 0], "rotationDelta": 0}]},
                        {"sourceRole": "feed", "sourceMechanismHash": "fb", "relativeTransforms": [{"delta": [-1, 0], "rotationDelta": 0}]},
                    ]
                }
            ],
        },
        "branches": [
            [_edge("feed", "fa", "conversion", "calc", "calcify", [1, 0])],
            [],
        ],
        "tail": [_edge("bonding", "bond", "output", "out", "delivered", [0, 1])],
    }
    layout = materialize_assembly_layout(candidate, fragment_index)
    assert layout["summary"]["layoutComplete"] is True
    assert layout["summary"]["instanceCount"] == 5
    placements = {item["instanceId"]: item for item in layout["placements"]}
    assert placements["convergence"]["anchorPosition"] == [0, 0]
    assert placements["branch-0:input"]["anchorPosition"] == [-1, 0]
    assert placements["branch-0:upstream-0"]["anchorPosition"] == [-2, 0]
    assert placements["branch-1:input"]["anchorPosition"] == [1, 0]
    assert placements["tail-0"]["anchorPosition"] == [0, 1]


def test_missing_geometry_is_reported_not_silently_ignored():
    candidate = {
        "convergence": {"targetRole": "bonding", "targetMechanismHash": "missing", "inputs": [], "samples": []},
        "branches": [],
        "tail": [],
    }
    layout = materialize_assembly_layout(candidate, {"fragments": []})
    assert layout["summary"]["layoutComplete"] is False
    assert layout["summary"]["missingGeometryCount"] == 1
