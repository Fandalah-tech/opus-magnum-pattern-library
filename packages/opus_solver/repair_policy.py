from __future__ import annotations

from typing import Any


GEOMETRY_FAILURE_MODES = {"blocked-input-at-start", "missing-standard-output"}
TIMING_FAILURE_MODES = {"no-product-delivered", "insufficient-product-delivery"}
COLLISION_WORDS = ("collision", "collides", "conflicting motion", "occupied")
TERMINAL_FAILURE_MODES = {"unavailable-parts"}


def recommend_repair_order(
    validation: dict[str, Any] | None,
    layout_summary: dict[str, Any] | None,
    *,
    temporal_enabled: bool,
    geometric_enabled: bool,
) -> dict[str, Any]:
    """Choose the cheapest plausible repair dimension from observed diagnostics.

    The policy is intentionally explainable and deterministic. It routes only
    between existing bounded repair searches; it does not change their search
    spaces or claim that a diagnostic proves the underlying cause.
    """
    validation = validation or {}
    layout_summary = layout_summary or {}
    failure_mode = str(validation.get("failureMode") or "")
    first_error = validation.get("firstError") or {}
    error_message = str(first_error.get("message") or "").lower()
    exact_conflicts = int(layout_summary.get("exactStaticConflictCount") or 0)
    blocked_inputs = list(validation.get("blockedInputsAtStart") or [])

    if failure_mode in TERMINAL_FAILURE_MODES:
        return {
            "preferred": "assembly",
            "order": [],
            "reason": f"failure-mode:{failure_mode}",
            "geometrySignals": [],
            "timingSignals": [],
            "failureMode": failure_mode,
        }

    geometry_signals = []
    timing_signals = []
    if blocked_inputs:
        geometry_signals.append("blocked-input-at-start")
    if exact_conflicts:
        geometry_signals.append("exact-static-footprint-conflict")
    if failure_mode in GEOMETRY_FAILURE_MODES:
        geometry_signals.append(f"failure-mode:{failure_mode}")
    if failure_mode == "simulation-error" and any(word in error_message for word in COLLISION_WORDS):
        geometry_signals.append("collision-like-engine-error")
    if failure_mode in TIMING_FAILURE_MODES:
        timing_signals.append(f"failure-mode:{failure_mode}")
    if failure_mode == "simulation-error" and not geometry_signals:
        timing_signals.append("non-collision-engine-error")

    if geometry_signals:
        preferred = "geometry"
        reason = geometry_signals[0]
    elif timing_signals:
        preferred = "timing"
        reason = timing_signals[0]
    else:
        preferred = "timing"
        reason = "default-local-repair"

    available = []
    if temporal_enabled:
        available.append("timing")
    if geometric_enabled:
        available.append("geometry")

    if not available:
        order = []
    elif preferred in available:
        order = [preferred] + [item for item in available if item != preferred]
    else:
        order = available

    return {
        "preferred": preferred,
        "order": order,
        "reason": reason,
        "geometrySignals": geometry_signals,
        "timingSignals": timing_signals,
        "failureMode": failure_mode or None,
    }
