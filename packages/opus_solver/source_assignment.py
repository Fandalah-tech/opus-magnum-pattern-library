from __future__ import annotations

from collections import defaultdict
from itertools import permutations
from typing import Any

from .manufacturing import ManufacturingOperation, ManufacturingPlan


_RELATION_BY_GLYPH = {
    "glyph-calcification": "calcify",
    "glyph-purification": "purify",
    "glyph-projection": "project",
    "glyph-animismus": "animate",
    "glyph-dispersion": "disperse",
    "glyph-unification": "unify",
    "glyph-duplication": "duplicate",
    "unbonder": "bond-removed",
}


def _branch_relations(candidate: dict[str, Any], branch_index: int) -> set[str]:
    branches = list(candidate.get("branches") or [])
    relations = {
        str(edge.get("relation") or "")
        for edge in (branches[branch_index] if branch_index < len(branches) else [])
        if edge.get("relation")
    }
    convergence = candidate.get("convergence") or {}
    inputs = list(convergence.get("inputs") or [])
    if branch_index < len(inputs):
        relations.update(str(value) for value in inputs[branch_index].get("relations", []) if value)
    return relations


def _interchangeable_reagent_groups(plan: ManufacturingPlan) -> list[set[int]]:
    groups: dict[str, set[int]] = {}
    for operation in plan.operations:
        if operation.kind != "source" or operation.metadata.get("reagentIndex") is None:
            continue
        group = str(operation.metadata.get("interchangeableSourceGroup") or "")
        if group:
            groups.setdefault(group, set()).add(int(operation.metadata["reagentIndex"]))
    return [indices for indices in groups.values() if indices]


def _operation_relation(operation: ManufacturingOperation) -> str | None:
    if operation.kind == "unbond" and operation.glyph == "unbonder":
        return "bond-removed"
    if operation.kind == "duplicate" and operation.glyph == "glyph-duplication":
        return "duplicate"
    if operation.kind == "transform":
        return _RELATION_BY_GLYPH.get(str(operation.glyph or ""))
    return None


def reagent_relation_profiles(plan: ManufacturingPlan) -> dict[int, list[set[str]]]:
    """Return pre-placement chemistry signatures reachable from each reagent feed.

    Generic manufacturing plans may contain many source operations even though a
    learned machine has only a few reusable feed lanes.  Each source operation is
    followed through its chemistry path until placement; this gives a target-side
    relation signature that can be matched to a learned branch without relying on
    historical input indices from the donor solution.
    """

    consumers: dict[str, list[ManufacturingOperation]] = defaultdict(list)
    for operation in plan.operations:
        for resource in operation.inputs:
            consumers[str(resource)].append(operation)

    result: dict[int, list[set[str]]] = defaultdict(list)
    for source in plan.operations:
        if source.kind != "source" or source.metadata.get("reagentIndex") is None:
            continue
        reagent_index = int(source.metadata["reagentIndex"])
        pending = [str(resource) for resource in source.outputs]
        seen_operations: set[str] = set()
        relations: set[str] = set()
        while pending:
            resource = pending.pop()
            for operation in consumers.get(resource, []):
                operation_id = str(operation.id)
                if operation_id in seen_operations:
                    continue
                seen_operations.add(operation_id)
                if operation.kind == "place":
                    continue
                relation = _operation_relation(operation)
                if relation:
                    relations.add(relation)
                # Product assembly and delivery are shared downstream mechanics,
                # not evidence about which target reagent should feed this lane.
                if operation.kind in {"bond", "deliver"}:
                    continue
                pending.extend(str(value) for value in operation.outputs)
        result[reagent_index].append(relations)
    return dict(result)


def _profile_score(branch_relations: set[str], profiles: list[set[str]]) -> tuple[int, int, int]:
    """Score a target reagent against one learned branch.

    Missing required pre-placement chemistry is strongly penalized.  Extra donor
    relations are tolerated because a coherent learned mechanism may contain
    reusable stages that the target plan does not need on every feed lane.
    """

    if not profiles:
        return (-10_000, 0, 0)
    best: tuple[int, int, int] | None = None
    for profile in profiles:
        matched = len(profile & branch_relations)
        missing = len(profile - branch_relations)
        extra = len(branch_relations - profile)
        score = 8 * matched - 20 * missing - extra
        candidate = (score, matched, -missing)
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    return best


def _generic_relation_assignment(
    candidate: dict[str, Any],
    plan: ManufacturingPlan,
    source_indices: list[int],
) -> dict[int, int] | None:
    branch_count = len(candidate.get("branches") or [])
    if branch_count <= 0 or not source_indices:
        return None
    if len(source_indices) > branch_count:
        return None

    profiles = reagent_relation_profiles(plan)
    branch_profiles = [_branch_relations(candidate, index) for index in range(branch_count)]

    if len(source_indices) == branch_count:
        best_assignment: dict[int, int] | None = None
        best_key: tuple[Any, ...] | None = None
        for permutation in permutations(source_indices):
            per_branch = [
                _profile_score(branch_profiles[index], profiles.get(reagent_index, []))
                for index, reagent_index in enumerate(permutation)
            ]
            total = sum(item[0] for item in per_branch)
            matched = sum(item[1] for item in per_branch)
            # Deterministic final tie-break keeps benchmark runs reproducible.
            key = (total, matched, tuple(-value for value in permutation))
            if best_key is None or key > best_key:
                best_key = key
                best_assignment = {index: reagent_index for index, reagent_index in enumerate(permutation)}
        return best_assignment

    # More learned lanes than distinct target reagents: assign the most
    # chemically compatible reagent independently to each reusable lane.
    assignment: dict[int, int] = {}
    for branch_index, branch_relations in enumerate(branch_profiles):
        ranked = sorted(
            (
                (_profile_score(branch_relations, profiles.get(reagent_index, [])), reagent_index)
                for reagent_index in source_indices
            ),
            key=lambda item: (item[0], -item[1]),
            reverse=True,
        )
        if not ranked:
            return None
        assignment[branch_index] = ranked[0][1]
    return assignment


def assign_branch_reagent_indices(candidate: dict[str, Any], plan: ManufacturingPlan) -> dict[int, int]:
    """Resolve learned feed branches to target reagent glyph indices.

    This extends the original specialized mapping with a generic chemistry-based
    assignment for manufacturing plans that source multiple non-interchangeable
    reagents.  It intentionally uses only the target manufacturing graph and the
    learned branch relation vocabulary; target solution bytes are never needed.
    """

    branch_count = len(candidate.get("branches") or [])
    if branch_count <= 0:
        return {}

    if plan.atom_flows:
        # Import lazily to avoid a module cycle while preserving the established
        # bonded-pair assignment semantics.
        from .candidate_solution import assign_branch_atom_flows

        return {
            branch_index: int(flow.reagent_index)
            for branch_index, flow in assign_branch_atom_flows(candidate, plan).items()
        }

    source_operations = [
        operation
        for operation in plan.operations
        if operation.kind == "source" and operation.metadata.get("reagentIndex") is not None
    ]
    if not source_operations:
        return {}

    source_indices = sorted({int(operation.metadata["reagentIndex"]) for operation in source_operations})
    if len(source_indices) == 1:
        return {branch_index: source_indices[0] for branch_index in range(branch_count)}

    interchangeable_groups = {
        str(operation.metadata.get("interchangeableSourceGroup") or "")
        for operation in source_operations
    } - {""}
    if (
        len(interchangeable_groups) == 1
        and all(operation.metadata.get("interchangeableSourceGroup") for operation in source_operations)
        and len(source_indices) == branch_count
    ):
        return {
            branch_index: reagent_index
            for branch_index, reagent_index in zip(range(branch_count), source_indices)
        }

    role_to_reagent = {
        str(operation.metadata.get("branchRole") or ""): int(operation.metadata["reagentIndex"])
        for operation in source_operations
        if operation.metadata.get("branchRole")
    }
    if set(role_to_reagent) == {"direct", "calcifying"} and branch_count == 2:
        calcifying_branches = [
            branch_index
            for branch_index in range(branch_count)
            if "calcify" in _branch_relations(candidate, branch_index)
        ]
        if len(calcifying_branches) != 1:
            raise ValueError(
                f"Expected exactly one calcifying source branch for {plan.strategy}; found {calcifying_branches}"
            )
        calcifying_index = calcifying_branches[0]
        direct_index = 1 - calcifying_index
        return {
            calcifying_index: role_to_reagent["calcifying"],
            direct_index: role_to_reagent["direct"],
        }

    generic = _generic_relation_assignment(candidate, plan, source_indices)
    if generic is not None:
        return generic
    raise ValueError(f"No source-branch reagent assignment strategy for manufacturing plan {plan.strategy}")


__all__ = ["assign_branch_reagent_indices", "reagent_relation_profiles"]
