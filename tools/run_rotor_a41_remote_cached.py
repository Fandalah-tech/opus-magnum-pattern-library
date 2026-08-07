from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.a41_validator_cache import ValidatorCache, solution_fingerprint
import tools.run_rotor_a41_remote_cycle_campaign as campaign

CACHE_PATH = Path("reports/rotor-a41-validator-cache.json")
CACHE_NAMESPACE = f"{campaign.VALIDATOR_URL.rstrip('/')}{campaign.ANALYZE_ENDPOINT}"


def main() -> int:
    cache = ValidatorCache(CACHE_PATH, CACHE_NAMESPACE)
    original_validate = campaign.validate_remote

    def validate_cached(puzzle_path: Path, solution: dict[str, Any], name: str) -> dict[str, Any]:
        fingerprint = solution_fingerprint(campaign.encode_solution(solution))
        cached = cache.get(fingerprint)
        if cached is not None:
            cached["cacheHit"] = True
            cached["fingerprint"] = fingerprint
            return cached

        result = original_validate(puzzle_path, solution, name)
        result["cacheHit"] = False
        result["fingerprint"] = fingerprint
        # Cache deterministic validator answers, including valid=False. Do not
        # cache transport failures/timeouts: those must be retried later.
        if result.get("ok"):
            stored = dict(result)
            stored.pop("cacheHit", None)
            cache.put(fingerprint, stored)
        return result

    campaign.validate_remote = validate_cached
    return campaign.main()


if __name__ == "__main__":
    raise SystemExit(main())
