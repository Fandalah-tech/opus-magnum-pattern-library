from __future__ import annotations

from collections import Counter
from typing import Any


GEOMETRY_FAILURE_MODES = {"blocked-input-at-start", "missing-standard-output"}
TIMING_FAILURE_MODES = {"no-product-delivered", "insufficient-product-delivery"}
COLLISION_WORDS = ("collision", "collides", "conflicting motion", "occupied")


def empirical_repair_evidence(
    outcome_index: dict[str, Any] | None,
    failure_mode: str,
    *,
    min_attempts: int = 12,
    min_rate_margin: float = 0.15,
) -> dict[str, Any]:
    """Estimate a repair preference from compact historical outcomes.

    Both timing and geometry must independently reach the minimum attempt count.
    This deliberately resists feedback loops from the deterministic router,
    because a frequently chosen first repair otherwise receives much more data.
    """
    attempts: Counter[str] = Counter()
    successes: Counter[str] = Counter()
    for record in (outcome_index or {}).get("outcomes", []):
        base_failure = str((record.get("baseProgress") or {}).get("failureMode") or "")
        if base_failure != failure_mode:
            continue
        for attempt in record.get("attempts", []):
            repair = str(attempt.get("repair") or "")
            if repair not in {"timing", "geometry"}:
                continue
            attempts[repair] += 1
            successes[repair] += int(bool(attempt.get("succeeded")))

    rates = {
        repair: (successes[repair] / attempts[repair] if attempts[repair] else 0.0)
        for repair in ("timing", "geometry")
    }
    sufficiently_observed = all(attempts[repair] >= max(1, int(min_attempts)) for repair in ("timing", "geometry"))
    winner = max(("timing", "geometry"), key=lambda repair: (rates[repair], successes[repair], repair))
    loser = "geometry" if winner == "timing" else "timing"
    margin = rates[winner] - rates[loser]
    usable = sufficiently_observed and margin >= max(0.0, float(min_rate_margin))
    return {
        "usable": usable,
        "preferred": winner if usable else None,
        "attempts": dict(sorted(attempts.items())),
        "successes": dict(sorted(successes.items())),
        "rates": {key: round(value, 6) for key, value in rates.items()},
        "rateMargin": round(margin, 6),
        "minAttempts": max(1, int(min_attempts)),
        "minRateMargin": float(min_rate_margin),
        "sufficientlyObserved": sufficiently_observed,
    }


def recommend_repair_order(
    validation: dict[str, Any] | None,
    layout_summary: dict[str, Any] | None,
    *,
    temporal_enabled: bool,
    geometric_enabled: bool,
    outcome_index: dict[str, Any] | None = None,
    learned_min_attempts: int = 12,
    learned_min_rate_margin: float = 0.15,
) -> dict[str, Any]:
    """Choose repair order from diagnostics, then conservative learned evidence.

    Strong geometry diagnostics remain authoritative. Learned evidence may only
    override ambiguous/timing/default preferences after both repair dimensions
    have enough independent attempts and a meaningful success-rate margin.
    """
    validation = validation or {}
    layout_summary = layout_summary or {}
    failure_mode = str(validation.get("failureMode") or "")
    first_error = validation.get("firstError") or {}
    error_message = str(first_error.get("message") or "").lower()
    exact_conflicts = int(layout_summary.get("exactStaticConflictCount") or 0)
    blocked_inputs = list(validation.get("blockedInputsAtStart") or [])

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
        diagnostic_strength = "strong"
    elif timing_signals:
        preferred = "timing"
        reason = timing_signals[0]
        diagnostic_strength = "weak"
    else:
        preferred = "timing"
        reason = "default-local-repair"
        diagnostic_strength = "weak"

    available = []
    if temporal_enabled:
        available.append("timing")
    if geometric_enabled:
        available.append("geometry")

    learned = empirical_repair_evidence(
        outcome_index,
        failure_mode,
        min_attempts=learned_min_attempts,
        min_rate_margin=learned_min_rate_margin,
    )
    learned_override = False
    if (
        diagnostic_strength != "strong"
        and learned.get("usable")
        and learned.get("preferred") in available
        and len(available) > 1
    ):
        preferred = str(learned["preferred"])
        reason = f"learned-prior:{failure_mode or '<none>'}"
        learned_override = True

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
        "diagnosticStrength": diagnostic_strength,
        "geometrySignals": geometry_signals,
        "timingSignals": timing_signals,
        "failureMode": failure_mode or None,
        "learnedOverride": learned_override,
        "learnedEvidence": learned,
    }
