from __future__ import annotations

from typing import Any

from .composition import rank_fragment_chains
from .manufacturing import ManufacturingPlan, build_manufacturing_plan


RELATION_BY_OPERATION = {
    ("transform", "glyph-calcification"): "calcify",
    ("bond", "bonder"): "bond-created",
    ("unbond", "unbonder"): "bond-removed",
    ("deliver", None): "delivered",
}
ROLE_BY_OPERATION = {
    "source": "feed",
    "transform": "conversion",
    "bond": "bonding",
    "unbond": "bonding",
    "deliver": "output",
    "dispose": "disposal",
}


def manufacturing_requirements(plan: ManufacturingPlan) -> dict[str, Any]:
    """Convert a manufacturing plan into fragment-flow requirements.

    Requirements intentionally describe *functional* coverage rather than
    geometry. Multiple source operations collapse to the same `feed` role;
    branching/merge multiplicity remains a later planner concern.
    """
    relations: list[str] = []
    roles: list[str] = []
    operation_kinds: list[str] = []

    for operation in plan.operations:
        operation_kinds.append(operation.kind)
        role = ROLE_BY_OPERATION.get(operation.kind)
        if role and role not in roles:
            roles.append(role)
        relation = RELATION_BY_OPERATION.get((operation.kind, operation.glyph))
        if relation and relation not in relations:
            relations.append(relation)

    return {
        "strategy": plan.strategy,
        "supported": plan.supported,
        "reason": plan.reason,
        "requiredRelations": relations,
        "requiredRoles": roles,
        "requiredGlyphs": list(plan.required_glyphs),
        "operationKinds": operation_kinds,
    }


def _chain_coverage(chain: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    observed_relations = [str(step.get("relation") or "") for step in chain.get("steps", [])]
    observed_roles = [str(node.get("role") or "") for node in chain.get("nodes", [])]

    required_relations = list(requirements.get("requiredRelations", []))
    required_roles = list(requirements.get("requiredRoles", []))
    missing_relations = [value for value in required_relations if value not in observed_relations]
    missing_roles = [value for value in required_roles if value not in observed_roles]

    relation_coverage = (
        (len(required_relations) - len(missing_relations)) / len(required_relations)
        if required_relations else 1.0
    )
    role_coverage = (
        (len(required_roles) - len(missing_roles)) / len(required_roles)
        if required_roles else 1.0
    )
    coverage_score = 0.75 * relation_coverage + 0.25 * role_coverage
    return {
        "complete": not missing_relations and not missing_roles,
        "score": round(coverage_score, 6),
        "relationCoverage": round(relation_coverage, 6),
        "roleCoverage": round(role_coverage, 6),
        "observedRelations": observed_relations,
        "observedRoles": observed_roles,
        "missingRelations": missing_relations,
        "missingRoles": missing_roles,
    }


def rank_target_fragment_chains(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    *,
    fragment_index: dict[str, Any] | None = None,
    max_depth: int = 6,
    limit: int = 25,
    min_observations: int = 1,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Rank empirical fragment chains against the target manufacturing plan."""
    plan = build_manufacturing_plan(puzzle)
    requirements = manufacturing_requirements(plan)
    if not plan.supported:
        return {
            "schemaVersion": "0.1.0",
            "manufacturingPlan": plan.to_dict(),
            "requirements": requirements,
            "summary": {
                "supported": False,
                "candidateCount": 0,
                "completeCandidateCount": 0,
                "reason": plan.reason,
            },
            "chains": [],
        }

    # Ask the empirical planner for a wider pool before target filtering.
    pool_limit = max(limit * 10, 100)
    empirical = rank_fragment_chains(
        flow_index,
        fragment_index=fragment_index,
        max_depth=max_depth,
        limit=pool_limit,
        min_observations=min_observations,
    )

    candidates: list[dict[str, Any]] = []
    complete_count = 0
    for chain in empirical:
        coverage = _chain_coverage(chain, requirements)
        if coverage["complete"]:
            complete_count += 1
        if require_complete and not coverage["complete"]:
            continue
        empirical_score = float(chain.get("score") or 0.0)
        # Target coverage dominates; empirical robustness breaks ties between
        # chains that satisfy the same chemistry plan.
        score = 0.65 * float(coverage["score"]) + 0.35 * empirical_score
        enriched = dict(chain)
        enriched["empiricalScore"] = round(empirical_score, 6)
        enriched["targetCoverage"] = coverage
        enriched["score"] = round(score, 6)
        candidates.append(enriched)

    candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            -float(item["targetCoverage"]["score"]),
            -float(item["empiricalScore"]),
            int(item.get("stepCount") or 0),
        )
    )
    selected = candidates[:max(0, int(limit))]
    return {
        "schemaVersion": "0.1.0",
        "manufacturingPlan": plan.to_dict(),
        "requirements": requirements,
        "summary": {
            "supported": True,
            "empiricalPoolCount": len(empirical),
            "completeCandidateCount": complete_count,
            "candidateCount": len(selected),
            "requireComplete": bool(require_complete),
            "bestScore": selected[0]["score"] if selected else None,
        },
        "chains": selected,
    }
