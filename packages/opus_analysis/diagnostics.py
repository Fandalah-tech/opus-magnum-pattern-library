from __future__ import annotations

from typing import Any


def analyze_solution(
    solution: dict[str, Any],
    graph: dict[str, Any],
    timeline: dict[str, Any],
    patterns: dict[str, Any],
) -> dict[str, Any]:
    """Produce conservative optimization diagnostics from static analyses.

    Findings describe measurable symptoms, not proven physical bottlenecks. Each
    diagnostic includes evidence and a recommended next inspection step.
    """
    diagnostics: list[dict[str, Any]] = []

    def add(
        diagnostic_id: str,
        severity: str,
        confidence: str,
        evidence: list[dict[str, Any]],
        targets: list[str] | None = None,
    ) -> None:
        diagnostics.append({
            "id": diagnostic_id,
            "severity": severity,
            "confidence": confidence,
            "targets": targets or [],
            "evidence": evidence,
        })

    timeline_summary = timeline.get("summary", {})
    arms = timeline.get("arms", [])
    horizon = max(1, timeline_summary.get("horizon", 1))

    idle_ratio = timeline_summary.get("globalIdleCycles", 0) / horizon
    if idle_ratio >= 0.25:
        add(
            "high-global-idle-time",
            "warning",
            "high",
            [{
                "kind": "timeline-summary",
                "globalIdleCycles": timeline_summary.get("globalIdleCycles"),
                "horizon": horizon,
                "idleRatio": round(idle_ratio, 4),
            }],
        )

    low_utilization = [
        arm for arm in arms
        if arm.get("actionCount", 0) > 0 and arm.get("utilization", 1) <= 0.15
    ]
    if low_utilization:
        add(
            "very-low-arm-utilization",
            "opportunity",
            "high",
            [{
                "kind": "timeline-arms",
                "arms": [{
                    "partId": arm.get("partId"),
                    "type": arm.get("type"),
                    "utilization": arm.get("utilization"),
                    "idleCycles": arm.get("idleCycles"),
                } for arm in low_utilization],
            }],
            [arm.get("partId") for arm in low_utilization if arm.get("partId")],
        )

    active_arms = [arm for arm in arms if arm.get("actionCount", 0) > 0]
    if len(active_arms) >= 2:
        utilizations = [arm.get("utilization", 0) for arm in active_arms]
        spread = max(utilizations) - min(utilizations)
        if spread >= 0.35:
            busiest = max(active_arms, key=lambda arm: arm.get("utilization", 0))
            lightest = min(active_arms, key=lambda arm: arm.get("utilization", 0))
            add(
                "unbalanced-arm-workload",
                "opportunity",
                "medium",
                [{
                    "kind": "utilization-spread",
                    "spread": round(spread, 4),
                    "busiest": {"partId": busiest.get("partId"), "utilization": busiest.get("utilization")},
                    "lightest": {"partId": lightest.get("partId"), "utilization": lightest.get("utilization")},
                }],
                [target for target in (busiest.get("partId"), lightest.get("partId")) if target],
            )

    peak = timeline_summary.get("peakParallelArms", 0)
    average = timeline_summary.get("averageParallelArms", 0)
    if len(active_arms) >= 2 and peak <= 1:
        add(
            "no-observed-program-parallelism",
            "warning",
            "high",
            [{"kind": "timeline-summary", "activeArms": len(active_arms), "peakParallelArms": peak}],
        )
    elif peak >= 2 and average < 1:
        add(
            "bursty-parallelism",
            "opportunity",
            "medium",
            [{"kind": "timeline-summary", "peakParallelArms": peak, "averageParallelArms": average}],
        )

    periods = [arm.get("period", 0) for arm in active_arms if arm.get("period", 0) > 0]
    if len(set(periods)) >= 3:
        add(
            "divergent-arm-periods",
            "info",
            "medium",
            [{"kind": "arm-periods", "periods": periods}],
        )

    graph_summary = graph.get("summary", {})
    if graph_summary.get("componentCount", 0) > 1:
        add(
            "independent-components-available",
            "opportunity",
            "medium",
            [{
                "kind": "graph-summary",
                "componentCount": graph_summary.get("componentCount"),
                "nodeCount": graph_summary.get("nodeCount"),
            }],
        )

    pattern_ids = {item.get("id") for item in patterns.get("findings", [])}
    if "sparse-arm-program" in pattern_ids and "parallel-arm-scheduling" not in pattern_ids:
        add(
            "sparse-arms-without-parallel-scheduling",
            "opportunity",
            "medium",
            [{"kind": "pattern-combination", "patterns": ["sparse-arm-program"]}],
        )

    diagnostics.sort(key=lambda item: (item["severity"], item["id"]))
    return {
        "schemaVersion": "0.1.0",
        "analysisType": "static-optimization-diagnostics",
        "limitations": [
            "Diagnostics use parsed structure and static program timing only.",
            "They do not prove molecule dependencies, collision constraints, or feasible instruction shifts.",
            "Recommendations must be validated by omsim after any solution mutation.",
        ],
        "summary": {
            "diagnosticCount": len(diagnostics),
            "warningCount": sum(1 for item in diagnostics if item["severity"] == "warning"),
            "opportunityCount": sum(1 for item in diagnostics if item["severity"] == "opportunity"),
            "infoCount": sum(1 for item in diagnostics if item["severity"] == "info"),
        },
        "diagnostics": diagnostics,
    }
