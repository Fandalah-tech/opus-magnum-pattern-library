from __future__ import annotations

import unittest

from packages.opus_solver import assign_branch_reagent_indices
from packages.opus_solver import candidate_solution as candidate_solution_module
from packages.opus_solver.manufacturing import ManufacturingOperation, ManufacturingPlan
from packages.opus_solver.source_assignment import reagent_relation_profiles


def _two_reagent_plan() -> ManufacturingPlan:
    return ManufacturingPlan(
        strategy="generic-reagent-chemistry-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=(
            ManufacturingOperation(
                id="source-direct",
                kind="source",
                inputs=(),
                outputs=("direct",),
                metadata={"reagentIndex": 0},
            ),
            ManufacturingOperation(
                id="place-direct",
                kind="place",
                inputs=("direct",),
                outputs=("product-a",),
            ),
            ManufacturingOperation(
                id="source-extracted",
                kind="source",
                inputs=(),
                outputs=("bonded",),
                metadata={"reagentIndex": 1},
            ),
            ManufacturingOperation(
                id="extract",
                kind="unbond",
                inputs=("bonded",),
                outputs=("extracted",),
                glyph="unbonder",
            ),
            ManufacturingOperation(
                id="place-extracted",
                kind="place",
                inputs=("extracted",),
                outputs=("product-b",),
            ),
            ManufacturingOperation(
                id="assemble",
                kind="bond",
                inputs=("product-a", "product-b"),
                outputs=("product",),
                glyph="bonder",
            ),
            ManufacturingOperation(
                id="deliver",
                kind="deliver",
                inputs=("product",),
                outputs=("output",),
            ),
        ),
        required_glyphs=("bonder", "unbonder"),
    )


def _candidate(first: set[str], second: set[str]) -> dict:
    return {
        "branches": [
            [{"relation": relation} for relation in sorted(first)],
            [{"relation": relation} for relation in sorted(second)],
        ],
        "convergence": {"inputs": [{"relations": []}, {"relations": []}]},
    }


class SourceAssignmentTests(unittest.TestCase):
    def test_reagent_profiles_follow_preplacement_chemistry(self) -> None:
        profiles = reagent_relation_profiles(_two_reagent_plan())
        self.assertEqual(profiles[0], [set()])
        self.assertEqual(profiles[1], [{"bond-removed"}])

    def test_generic_assignment_matches_extraction_branch(self) -> None:
        assignment = assign_branch_reagent_indices(
            _candidate(set(), {"bond-removed"}),
            _two_reagent_plan(),
        )
        self.assertEqual(assignment, {0: 0, 1: 1})

    def test_generic_assignment_reverses_with_branch_chemistry(self) -> None:
        assignment = assign_branch_reagent_indices(
            _candidate({"bond-removed"}, set()),
            _two_reagent_plan(),
        )
        self.assertEqual(assignment, {0: 1, 1: 0})

    def test_extra_donor_relations_do_not_hide_required_match(self) -> None:
        assignment = assign_branch_reagent_indices(
            _candidate(set(), {"bond-removed", "project"}),
            _two_reagent_plan(),
        )
        self.assertEqual(assignment, {0: 0, 1: 1})

    def test_single_target_reagent_can_feed_multiple_learned_lanes(self) -> None:
        plan = ManufacturingPlan(
            strategy="generic-reagent-chemistry-v1",
            supported=True,
            reason=None,
            product_index=0,
            atom_flows=(),
            operations=(
                ManufacturingOperation(
                    id="source",
                    kind="source",
                    inputs=(),
                    outputs=("feed",),
                    metadata={"reagentIndex": 2},
                ),
            ),
            required_glyphs=(),
        )
        assignment = assign_branch_reagent_indices(_candidate(set(), set()), plan)
        self.assertEqual(assignment, {0: 2, 1: 2})

    def test_candidate_materializer_is_wired_to_generic_mapper(self) -> None:
        self.assertIs(candidate_solution_module.assign_branch_reagent_indices, assign_branch_reagent_indices)


if __name__ == "__main__":
    unittest.main()
