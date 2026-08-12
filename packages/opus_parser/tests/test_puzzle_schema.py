from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from typing import Any

from packages.opus_parser import parse_puzzle_bytes
from packages.opus_parser.tests.test_parsers import puzzle_with_reagent_bond


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PUZZLE_SCHEMA = json.loads(
    (REPOSITORY_ROOT / "schemas" / "puzzle.schema.json").read_text(encoding="utf-8")
)


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise AssertionError(f"Test validator only supports local references: {ref}")
    value: Any = root
    for token in ref[2:].split("/"):
        value = value[token.replace("~1", "/").replace("~0", "~")]
    return value


def _assert_schema_shape(
    schema: dict[str, Any], value: Any, *, root: dict[str, Any], path: str = "$"
) -> None:
    if "$ref" in schema:
        _assert_schema_shape(_resolve_ref(root, schema["$ref"]), value, root=root, path=path)
        return

    if "const" in schema:
        assert value == schema["const"], f"{path}: expected {schema['const']!r}, got {value!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} is not in {schema['enum']!r}"

    expected_types = schema.get("type")
    if expected_types:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        matches = {
            "array": lambda item: isinstance(item, list),
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "null": lambda item: item is None,
            "object": lambda item: isinstance(item, dict),
            "string": lambda item: isinstance(item, str),
        }
        assert any(matches[kind](value) for kind in expected_types), (
            f"{path}: expected type {expected_types!r}, got {type(value).__name__}"
        )

    if isinstance(value, dict):
        required = set(schema.get("required", []))
        assert required <= value.keys(), f"{path}: missing {sorted(required - value.keys())!r}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = value.keys() - properties.keys()
            assert not extra, f"{path}: unexpected {sorted(extra)!r}"
        for key, item in value.items():
            if key in properties:
                _assert_schema_shape(properties[key], item, root=root, path=f"{path}.{key}")

    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"], f"{path}: too few items"
        if "maxItems" in schema:
            assert len(value) <= schema["maxItems"], f"{path}: too many items"
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            assert len(serialized) == len(set(serialized)), f"{path}: duplicate items"
        if "items" in schema:
            for index, item in enumerate(value):
                _assert_schema_shape(schema["items"], item, root=root, path=f"{path}[{index}]")

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema:
            assert value >= schema["minimum"], f"{path}: below minimum"
        if "maximum" in schema:
            assert value <= schema["maximum"], f"{path}: above maximum"

    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{path}: shorter than minLength"
        if "pattern" in schema:
            assert re.search(schema["pattern"], value), f"{path}: does not match pattern"


class PuzzleSchemaTests(unittest.TestCase):
    def test_schema_matches_normal_and_triplex_parser_outputs(self):
        for source_name, bond_code in (("normal.puzzle", 1), (None, 14), ("yellow.puzzle", 8)):
            with self.subTest(source_name=source_name, bond_code=bond_code):
                puzzle = parse_puzzle_bytes(
                    puzzle_with_reagent_bond(bond_code), source_name=source_name
                )
                _assert_schema_shape(PUZZLE_SCHEMA, puzzle, root=PUZZLE_SCHEMA)


if __name__ == "__main__":
    unittest.main()
