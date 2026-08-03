from __future__ import annotations

import hashlib
from pathlib import Path

from .binary import BinaryReader, ParseError, read_bytes

ELEMENTS = {
    1: "salt", 2: "air", 3: "earth", 4: "fire", 5: "water", 6: "quicksilver",
    7: "gold", 8: "silver", 9: "copper", 10: "iron", 11: "tin", 12: "lead",
    13: "vitae", 14: "mors", 15: "repeat", 16: "quintessence",
}
BONDS = {1: "normal", 14: "triplex"}
GLYPH_FLAGS = {
    0x0001: ["bonder"], 0x0002: ["unbonder"], 0x0004: ["multibonder"],
    0x0008: ["triplex-bonder"], 0x0010: ["calcification"],
    0x0020: ["duplication"], 0x0040: ["projection"], 0x0080: ["purification"],
    0x0100: ["animismus"], 0x0200: ["disposal"],
    0x0400: ["unification", "dispersion"],
}


def _molecule(reader: BinaryReader, kind: str, index: int) -> dict:
    atoms = []
    atom_count = reader.int32()
    if atom_count < 0 or atom_count > 100000:
        raise ParseError(f"Invalid atom count {atom_count} for {kind} {index}")
    positions: set[tuple[int, int]] = set()
    for atom_index in range(atom_count):
        element_code = reader.byte()
        if element_code not in ELEMENTS:
            raise ParseError(f"Unknown element code {element_code} in {kind} {index}")
        position = (reader.sbyte(), reader.sbyte())
        if position in positions:
            raise ParseError(f"Duplicate atom position {position} in {kind} {index}")
        positions.add(position)
        atoms.append({"id": f"a{atom_index}", "element": ELEMENTS[element_code], "position": list(position)})

    bonds = []
    bond_count = reader.int32()
    if bond_count < 0 or bond_count > 100000:
        raise ParseError(f"Invalid bond count {bond_count} for {kind} {index}")
    for bond_index in range(bond_count):
        bond_code = reader.byte()
        if bond_code not in BONDS:
            raise ParseError(f"Unknown bond code {bond_code} in {kind} {index}")
        start = (reader.sbyte(), reader.sbyte())
        end = (reader.sbyte(), reader.sbyte())
        if start not in positions or end not in positions:
            raise ParseError(f"Bond {bond_index} references a missing atom in {kind} {index}")
        bonds.append({"type": BONDS[bond_code], "from": list(start), "to": list(end)})

    return {"id": f"{kind}-{index}", "atoms": atoms, "bonds": bonds}


def _parts(flags: int) -> dict:
    glyph_bits = (flags >> 8) & 0xFFF
    glyphs = ["equilibrium"]
    remaining = glyph_bits
    for flag, names in GLYPH_FLAGS.items():
        if glyph_bits & flag:
            glyphs.extend(names)
            remaining &= ~flag
    arms = ["arm1", "arm2", "arm3", "arm6", "piston"]
    if (flags >> 24) & 0x10:
        arms.append("van-berlo")
    return {"rawFlags": flags, "arms": arms, "glyphs": glyphs, "unknownGlyphFlags": remaining}


def parse_puzzle_bytes(data: bytes, *, source_name: str | None = None) -> dict:
    reader = BinaryReader(data)
    version = reader.int32()
    if version != 3:
        raise ParseError(f"Unsupported puzzle version {version}; expected 3")
    name = reader.string()
    creator_id = reader.uint64()
    flags = reader.uint64()
    reagent_count = reader.int32()
    if reagent_count < 0 or reagent_count > 10000:
        raise ParseError(f"Invalid reagent count {reagent_count}")
    reagents = [_molecule(reader, "reagent", i) for i in range(reagent_count)]
    product_count = reader.int32()
    if product_count < 0 or product_count > 10000:
        raise ParseError(f"Invalid product count {product_count}")
    products = [_molecule(reader, "product", i) for i in range(product_count)]
    output_scale = reader.int32()
    production = reader.boolean()

    return {
        "schemaVersion": "0.1.0",
        "format": {"kind": "puzzle", "version": version},
        "source": {
            "name": source_name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        },
        "name": name,
        "creatorId": str(creator_id),
        "availableParts": _parts(flags),
        "reagents": reagents,
        "products": products,
        "outputScale": output_scale,
        "production": production,
        "trailingBytes": reader.remaining(),
    }


def parse_puzzle(source: str | Path | bytes | bytearray) -> dict:
    data = read_bytes(source)
    name = None if isinstance(source, (bytes, bytearray)) else Path(source).name
    return parse_puzzle_bytes(data, source_name=name)
