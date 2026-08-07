from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import tools.run_rotor_a41_remote_cached as cached

OUTPUT = Path("reports/rotor-a41-search-plan.json")


def build_plan() -> dict:
    solution, source, match_kind = cached.campaign.load_reference()
    if solution is None:
        raise RuntimeError("A41 reference unavailable")
    base = cached.campaign.candidate_shifts(solution)
    expanded = cached.expand_idle_window_shifts(solution, base, max_jump=cached.MAX_IDLE_JUMP)

    by_part = Counter(str(item.get("part") or "unknown") for item in expanded)
    by_instruction = Counter(str(item.get("instruction") or "unknown") for item in expanded)
    by_jump = Counter(int(item.get("jump") or 1) for item in expanded)
    by_group = Counter(
        f"{item.get('part') or 'unknown'}::{item.get('instruction') or 'unknown'}"
        for item in expanded
    )

    return {
        "schemaVersion": 1,
        "referenceSource": source,
        "referenceMatch": match_kind,
        "referenceMetrics": solution.get("metrics") or {},
        "maxIdleJump": cached.MAX_IDLE_JUMP,
        "baseCandidateCount": len(base),
        "expandedCandidateCount": len(expanded),
        "campaignBudget": cached.campaign.MAX_CANDIDATES,
        "budgetRemaining": cached.campaign.MAX_CANDIDATES - len(expanded),
        "byPart": dict(sorted(by_part.items())),
        "byInstruction": dict(sorted(by_instruction.items())),
        "byJump": {str(key): value for key, value in sorted(by_jump.items())},
        "byPartInstruction": dict(sorted(by_group.items())),
    }


def main() -> int:
    plan = build_plan()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    if plan["expandedCandidateCount"] > plan["campaignBudget"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
