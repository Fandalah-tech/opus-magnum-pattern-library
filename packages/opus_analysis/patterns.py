from __future__ import annotations

from collections import Counter
from typing import Any

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
ROTATION_INSTRUCTIONS = {"rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw"}
TRACK_INSTRUCTIONS = {"track_plus", "track_minus"}


def _part_counts(solution: dict[str, Any]) -> Counter[str]:
    return Counter(part.get("type", "unknown") for part in solution.get("parts", []))


def _arms(solution: dict[str, Any]) -> list[dict[str, Any]]:
    return [part for part in solution.get("parts", []) if part.get("type") in ARM_TYPES]


def _instructions(arm: dict[str, Any]) -> Counter[str]:
    return Counter(item.get("instruction", "unknown") for item in arm.get("program", []))


def detect_patterns(solution: dict[str, Any], graph: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    """Detect conservative, explainable solution patterns.

    Detectors in this first version use only parsed structure and static program
    information. Every finding includes evidence and a confidence level. No
    detector claims physical molecule behavior without a simulator trace.
    """
    counts = _part_counts(solution)
    arms = _arms(solution)
    findings: list[dict[str, Any]] = []

    def add(pattern_id: str, confidence: str, evidence: list[dict[str, Any]], scope: str = "solution") -> None:
        findings.append({
            "id": pattern_id,
            "confidence": confidence,
            "scope": scope,
            "evidence": evidence,
        })

    if counts.get("track", 0):
        tracked_arms = []
        for arm in arms:
            histogram = _instructions(arm)
            moves = sum(histogram.get(name, 0) for name in TRACK_INSTRUCTIONS)
            if moves:
                tracked_arms.append({"partId": arm.get("id"), "trackMoves": moves})
        if tracked_arms:
            add("track-transport", "high", [
                {"kind": "part-count", "partType": "track", "value": counts["track"]},
                {"kind": "arm-programs", "arms": tracked_arms},
            ])

    piston_arms = [arm for arm in arms if arm.get("type") == "piston"]
    if piston_arms:
        add("variable-reach-arm", "high", [{
            "kind": "parts", "partIds": [arm.get("id") for arm in piston_arms], "partType": "piston"
        }])

    van_berlo = [arm for arm in arms if arm.get("type") == "baron"]
    if van_berlo:
        add("van-berlo-arm", "high", [{
            "kind": "parts", "partIds": [arm.get("id") for arm in van_berlo], "partType": "baron"
        }])

    oscillators = []
    for arm in arms:
        histogram = _instructions(arm)
        clockwise = histogram.get("rotate_cw", 0) + histogram.get("pivot_cw", 0)
        counter = histogram.get("rotate_ccw", 0) + histogram.get("pivot_ccw", 0)
        if clockwise and counter:
            oscillators.append({"partId": arm.get("id"), "clockwise": clockwise, "counterClockwise": counter})
    if oscillators:
        add("bidirectional-oscillation", "medium", [{"kind": "arm-programs", "arms": oscillators}])

    repeaters = []
    for arm in arms:
        histogram = _instructions(arm)
        controls = histogram.get("repeat", 0) + histogram.get("period_override", 0)
        if controls:
            repeaters.append({"partId": arm.get("id"), "controlInstructions": controls})
    if repeaters:
        add("explicit-periodic-program", "high", [{"kind": "arm-programs", "arms": repeaters}])

    graph_summary = graph.get("summary", {})
    if graph_summary.get("componentCount", 0) > 1:
        add("independent-structural-components", "medium", [{
            "kind": "graph-summary",
            "componentCount": graph_summary.get("componentCount"),
            "nodeCount": graph_summary.get("nodeCount"),
        }])

    timeline_summary = timeline.get("summary", {})
    if timeline_summary.get("peakParallelArms", 0) >= 2:
        add("parallel-arm-scheduling", "high", [{
            "kind": "timeline-summary",
            "peakParallelArms": timeline_summary.get("peakParallelArms"),
            "averageParallelArms": timeline_summary.get("averageParallelArms"),
        }])

    sparse_arms = []
    for arm in timeline.get("arms", []):
        if arm.get("actionCount", 0) and arm.get("utilization", 1) <= 0.2:
            sparse_arms.append({
                "partId": arm.get("partId"),
                "utilization": arm.get("utilization"),
                "idleCycles": arm.get("idleCycles"),
            })
    if sparse_arms:
        add("sparse-arm-program", "medium", [{"kind": "timeline-arms", "arms": sparse_arms}])

    findings.sort(key=lambda item: (item["id"], item["scope"]))
    return {
        "schemaVersion": "0.1.0",
        "analysisType": "explainable-pattern-detection",
        "limitations": [
            "Detectors use static structure and program data only.",
            "Physical transfers, collisions and molecule storage are not yet traced.",
            "Medium-confidence findings are hypotheses intended for human review.",
        ],
        "summary": {
            "findingCount": len(findings),
            "highConfidenceCount": sum(1 for item in findings if item["confidence"] == "high"),
            "mediumConfidenceCount": sum(1 for item in findings if item["confidence"] == "medium"),
        },
        "findings": findings,
    }
