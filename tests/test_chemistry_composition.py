from packages.opus_solver.chemistry_composition import (
    manufacturing_requirements,
    rank_chains_for_manufacturing_plan,
    required_flow_relations,
)
from packages.opus_solver.manufacturing import ManufacturingOperation, ManufacturingPlan


def _plan() -> ManufacturingPlan:
    return ManufacturingPlan(
        strategy="test",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(
            ManufacturingOperation(id="s1", kind="source", inputs=(), outputs=("a",)),
            ManufacturingOperation(id="s2", kind="source", inputs=(), outputs=("b",)),
            ManufacturingOperation(id="c", kind="transform", inputs=("a",), outputs=("c",), glyph="glyph-calcification"),
            ManufacturingOperation(id="b", kind="bond", inputs=("c", "b"), outputs=("m",), glyph="bonder"),
            ManufacturingOperation(id="d", kind="deliver", inputs=("m",), outputs=("o",)),
        ),
        required_glyphs=("bonder", "glyph-calcification"),
    )


def _flow(relations):
    transitions = []
    previous_role = "feed"
    previous_hash = "f"
    role_for = {"calcify": "conversion", "bond-created": "bonding", "delivered": "output"}
    for index, relation in enumerate(relations):
        target_role = role_for[relation]
        target_hash = f"h{index}"
        transitions.append({
            "sourceRole": previous_role,
            "sourceMechanismHash": previous_hash,
            "targetRole": target_role,
            "targetMechanismHash": target_hash,
            "relation": relation,
            "observationCount": 5,
            "sourcePuzzleCount": 3,
            "sourceSolutionCount": 4,
        })
        previous_role, previous_hash = target_role, target_hash
    return {"transitions": transitions}


def test_required_relations_ignore_transport_operations():
    assert required_flow_relations(_plan()) == {"calcify": 1, "bond-created": 1, "delivered": 1}


def test_requirements_report_multi_source_convergence():
    requirements = manufacturing_requirements(_plan())
    assert requirements["sourceCount"] == 2
    assert requirements["requiresConvergence"] is True


def test_full_functional_chain_is_retained_but_not_assembly_complete():
    ranked = rank_chains_for_manufacturing_plan(_plan(), _flow(["calcify", "bond-created", "delivered"]))
    assert len(ranked) == 1
    assert ranked[0]["functionalCoverageScore"] == 1.0
    assert ranked[0]["manufacturing"]["coverage"]["missing"] == {}
    assert ranked[0]["manufacturing"]["assemblyComplete"] is False


def test_missing_required_relation_is_filtered_by_default():
    ranked = rank_chains_for_manufacturing_plan(_plan(), _flow(["bond-created", "delivered"]))
    assert ranked == []


def test_partial_coverage_can_be_kept_for_diagnostics():
    ranked = rank_chains_for_manufacturing_plan(
        _plan(),
        _flow(["bond-created", "delivered"]),
        require_full_functional_coverage=False,
    )
    assert len(ranked) == 1
    assert ranked[0]["manufacturing"]["coverage"]["missing"] == {"calcify": 1}
    assert ranked[0]["functionalCoverageScore"] < 1.0
