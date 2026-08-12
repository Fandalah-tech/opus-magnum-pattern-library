from __future__ import annotations

from collections import Counter
from typing import Any

from .composition import rank_fragment_chains
from .manufacturing import ManufacturingPlan, build_manufacturing_plan


_OPERATION_RELATIONS = {
    "transform": {
        "glyph-calcification": "calcify",
    },
    "bond": {
        "bonder": "bond-created",
        "unbonder": "bond-removed",
    },
    "unbond": {
        "unbonder": "bond-removed",
    },
    "duplicate": {
        "glyph-duplication": "duplicate",
    },
    "deliver": {None: "delivered"},
}


def required_flow_relations(plan: ManufacturingPlan) -> Counter[str]:
    """Translate manufacturing operations into replay-observable flow relations.

    Source and placement operations are transport/availability requirements and
    therefore do not become functional fragment-flow relations. They are kept
    separately in the requirement summary so a linear chain is never mistaken
    for a complete multi-feed assembly plan.
    """
    relations: Counter[str] = Counter()
    for operation in plan.operations:
        if operation.kind == "bond" and operation.glyph == "bonder-prisma":
            channels = operation.metadata.get("triplexChannels") or ("red", "black", "yellow")
            for channel in channels:
                relations[f"triplex-bond-created:{channel}"] += 1
            continue
        mapping = _OPERATION_RELATIONS.get(operation.kind)
        if not mapping:
            continue
        relation = mapping.get(operation.glyph)
        if relation is None and operation.kind == "deliver":
            relation = mapping.get(None)
        if relation:
            relations[relation] += 1
    return relations


def manufacturing_requirements(plan: ManufacturingPlan) -> dict[str, Any]:
    sources = [operation for operation in plan.operations if operation.kind == "source"]
    placements = [operation for operation in plan.operations if operation.kind == "place"]
    return {
        "supported": plan.supported,
        "strategy": plan.strategy,
        "reason": plan.reason,
        "requiredRelations": dict(sorted(required_flow_relations(plan).items())),
        "requiredGlyphs": list(plan.required_glyphs),
        "sourceCount": len(sources),
        "placementCount": len(placements),
        "requiresConvergence": len(sources) > 1,
    }


def _relation_coverage(required: Counter[str], observed: Counter[str]) -> dict[str, Any]:
    required_total = sum(required.values())
    matched = Counter({key: min(count, observed.get(key, 0)) for key, count in required.items()})
    matched_total = sum(matched.values())
    missing = Counter({key: count - matched.get(key, 0) for key, count in required.items() if count > matched.get(key, 0)})
    extra = Counter({key: count - required.get(key, 0) for key, count in observed.items() if count > required.get(key, 0)})
    return {
        "score": 1.0 if required_total == 0 else round(matched_total / required_total, 6),
        "matched": dict(sorted((key, value) for key, value in matched.items() if value)),
        "missing": dict(sorted(missing.items())),
        "extra": dict(sorted(extra.items())),
        "requiredCount": required_total,
        "matchedCount": matched_total,
    }


def rank_chains_for_manufacturing_plan(
    plan: ManufacturingPlan,
    flow_index: dict[str, Any],
    *,
    fragment_index: dict[str, Any] | None = None,
    max_depth: int = 6,
    limit: int = 25,
    candidate_pool: int = 5000,
    min_observations: int = 1,
    require_full_functional_coverage: bool = True,
    min_engine_validated_solutions: int = 0,
) -> list[dict[str, Any]]:
    """Rank empirical fragment chains against a manufacturing plan.

    This validates functional transformation coverage only. A linear chain
    cannot prove multi-source convergence, so candidates expose an explicit
    `assemblyComplete` flag which remains false when the manufacturing plan
    requires more than one source.
    """
    if not plan.supported:
        return []

    required = required_flow_relations(plan)
    requirements = manufacturing_requirements(plan)
    candidates = rank_fragment_chains(
        flow_index,
        fragment_index=fragment_index,
        max_depth=max_depth,
        limit=max(limit, candidate_pool),
        min_observations=min_observations,
        min_engine_validated_solutions=min_engine_validated_solutions,
        allowed_relations=required.keys() if required else None,
    )

    ranked = []
    for chain in candidates:
        observed = Counter(str(step.get("relation") or "") for step in chain.get("steps", []) if step.get("relation"))
        coverage = _relation_coverage(required, observed)
        if require_full_functional_coverage and coverage["missing"]:
            continue

        empirical = float(chain.get("score") or 0.0)
        coverage_score = float(coverage["score"])
        # Functional correctness dominates historical popularity. A chain with
        # incomplete chemistry must not outrank a complete but rarer chain.
        score = 0.72 * coverage_score + 0.28 * empirical
        assembly_complete = not bool(requirements["requiresConvergence"])

        item = dict(chain)
        item["manufacturing"] = {
            "requirements": requirements,
            "coverage": coverage,
            "assemblyComplete": assembly_complete,
            "assemblyLimitation": None if assembly_complete else "linear-chain-cannot-prove-multi-source-convergence",
        }
        item["empiricalScore"] = round(empirical, 6)
        item["functionalCoverageScore"] = round(coverage_score, 6)
        item["score"] = round(score, 6)
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            -float(item["functionalCoverageScore"]),
            -float(item["score"]),
            int(item.get("stepCount") or 0),
        )
    )
    return ranked[:max(0, int(limit))]


def plan_puzzle_fragment_chains(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    *,
    fragment_index: dict[str, Any] | None = None,
    max_depth: int = 6,
    limit: int = 25,
    min_observations: int = 1,
    min_engine_validated_solutions: int = 0,
) -> dict[str, Any]:
    plan = build_manufacturing_plan(puzzle)
    requirements = manufacturing_requirements(plan)
    chains = rank_chains_for_manufacturing_plan(
        plan,
        flow_index,
        fragment_index=fragment_index,
        max_depth=max_depth,
        limit=limit,
        min_observations=min_observations,
        min_engine_validated_solutions=min_engine_validated_solutions,
    ) if plan.supported else []
    return {
        "schemaVersion": "0.1.0",
        "manufacturingPlan": plan.to_dict(),
        "requirements": requirements,
        "summary": {
            "supported": plan.supported,
            "candidateCount": len(chains),
            "functionallyCompleteCandidateCount": sum(not item["manufacturing"]["coverage"]["missing"] for item in chains),
            "assemblyCompleteCandidateCount": sum(bool(item["manufacturing"]["assemblyComplete"]) for item in chains),
            "bestScore": chains[0]["score"] if chains else None,
            "engineValidatedCandidateCount": sum(
                all(int(step.get("engineValidatedSolutionCount") or 0) > 0 for step in item.get("steps", []))
                for item in chains
            ),
        },
        "chains": chains,
    }
