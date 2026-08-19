from __future__ import annotations

from copy import deepcopy
from typing import Any


def enforce_puzzle_product_contract(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    validation: dict[str, Any],
    *,
    target: int,
) -> dict[str, Any]:
    """Require generated candidates to expose and complete every puzzle product.

    The legacy local validator inferred the required product set from output
    glyphs already present in the generated solution. That is unsafe for blind
    composition: omitting an output glyph silently removed the corresponding
    puzzle product from the completion contract. The puzzle definition is the
    authority instead.
    """

    result = deepcopy(validation)
    expected_products = list(range(len(puzzle.get("products") or [])))
    standard_outputs = [
        (str(part.get("id") or ""), int(part.get("which") or 0))
        for part in solution.get("parts", [])
        if str(part.get("type") or "") == "out-std"
    ]
    outputs_by_product = {
        product_index: [
            output_id
            for output_id, output_product in standard_outputs
            if output_product == product_index
        ]
        for product_index in expected_products
    }
    missing = [
        product_index
        for product_index in expected_products
        if not outputs_by_product.get(product_index)
    ]

    delivered_by_product = {
        int(key): int(value)
        for key, value in (result.get("deliveredByProduct") or {}).items()
    }
    for product_index in expected_products:
        delivered_by_product.setdefault(product_index, 0)
    deficits = {
        str(product_index): max(
            0,
            int(target) - int(delivered_by_product.get(product_index, 0)),
        )
        for product_index in expected_products
    }

    product_contract_complete = bool(expected_products) and not missing and all(
        value == 0 for value in deficits.values()
    )
    legacy_complete = bool(result.get("complete"))
    result.update({
        "expectedProductIndices": expected_products,
        "outputGlyphsByProduct": {
            str(key): value for key, value in sorted(outputs_by_product.items())
        },
        "missingProductOutputIndices": missing,
        "productOutputContractComplete": product_contract_complete,
        "legacyOutputDerivedComplete": legacy_complete,
        "deliveredByProduct": {
            str(key): value for key, value in sorted(delivered_by_product.items())
        },
        "outputDeficits": deficits,
        "totalDeficit": sum(deficits.values()),
    })

    # Preserve unavailable-part diagnostics, but otherwise missing output glyphs
    # are a structural blocker that should be visible before downstream motion
    # errors. A collision can still be inspected in firstError/terminated flags.
    if missing:
        result["complete"] = False
        if result.get("failureMode") != "unavailable-parts":
            result["failureMode"] = "missing-product-output"
    elif not product_contract_complete:
        result["complete"] = False
    else:
        result["complete"] = bool(legacy_complete)
    return result


__all__ = ["enforce_puzzle_product_contract"]
