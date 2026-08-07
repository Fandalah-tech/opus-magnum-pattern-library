from __future__ import annotations

from dataclasses import dataclass

from .fragment_planner import FragmentAssemblyPlan, STANDARD_PRODUCT_TARGET


@dataclass(frozen=True, slots=True)
class CycleBound:
    mode: str
    n: int
    d: int
    latency: int
    cycles: int


def classical_cycle_bound(
    plan: FragmentAssemblyPlan,
    *,
    latency: int,
    target_products: int = STANDARD_PRODUCT_TARGET,
    final_output_cycle: int = 1,
) -> CycleBound:
    """Traditional non-overlap bound: 2N + L + final output cycle."""
    n = plan.input_bound_n(target_products=target_products)
    return CycleBound(
        mode="classical",
        n=n,
        d=0,
        latency=latency,
        cycles=2 * n + latency + final_output_cycle,
    )


def overlap_cycle_bound(
    plan: FragmentAssemblyPlan,
    *,
    latency: int,
    double_consumptions: int = 0,
    target_products: int = STANDARD_PRODUCT_TARGET,
) -> CycleBound:
    """Overlap-theory bound: N - D + L.

    In overlap cycle theory, inputs/glyphs/outputs are evaluated on both sides
    of the movement phase. N is still the limiting number of input sets, D is
    the number of useful double-consumptions of that limiting input, and L is
    latency from the final required spawn to completion.

    D is explicit rather than guessed: proving a double-consume is a geometric
    and sub-cycle scheduling problem and must be demonstrated by a candidate.
    """
    n = plan.input_bound_n(target_products=target_products)
    d = max(0, int(double_consumptions))
    if d > n:
        raise ValueError("double_consumptions cannot exceed N")
    return CycleBound(
        mode="overlap",
        n=n,
        d=d,
        latency=latency,
        cycles=n - d + latency,
    )
