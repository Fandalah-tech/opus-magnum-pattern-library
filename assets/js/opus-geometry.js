(() => {
  const DIRECTIONS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];

  // Canonical rot=0 occupied cells. Confirmed footprints come from public
  // Opus Magnum tooling conventions; unknown parts deliberately fall back to
  // one cell rather than claiming false precision.
  const FOOTPRINTS = {
    bonder: [[0, 0], [1, 0]],
    unbonder: [[0, 0], [1, 0]],
    "bonder-speed": [[0, 0], [1, 0], [0, -1], [-1, 1]],
    "glyph-calcification": [[0, 0]],
    "glyph-equilibrium": [[0, 0]],
    "glyph-disposal": [[0, 0], [1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]],
    "glyph-projection": [[0, 0], [1, 0]],
    "glyph-purification": [[0, 0], [1, 0], [2, 0]],
    "glyph-duplication": [[0, 0], [1, 0]],
    "glyph-life-and-death": [[0, 0], [1, 0]],
    "glyph-marker": [[0, 0]],
    "glyph-bonder-prisma": [[0, 0], [1, 0], [0, 1]],
    "glyph-unbonder-prisma": [[0, 0], [1, 0], [0, 1]],
  };

  const LABELS = {
    bonder: "B", unbonder: "U", "bonder-speed": "MB",
    "glyph-calcification": "C", "glyph-equilibrium": "E", "glyph-disposal": "D",
    "glyph-projection": "P", "glyph-purification": "PU", "glyph-duplication": "DU",
    "glyph-life-and-death": "LD", "glyph-marker": "M",
    "glyph-bonder-prisma": "PB", "glyph-unbonder-prisma": "PU",
    input: "IN", "out-std": "OUT", "out-rep": "OUT",
  };

  function add(a, b) { return [a[0] + b[0], a[1] + b[1]]; }

  // Positive rotations follow the file/game convention: E -> NE -> NW.
  function rotateCell([q, r], rotation = 0) {
    let result = [q, r];
    const turns = ((Number(rotation) % 6) + 6) % 6;
    for (let i = 0; i < turns; i += 1) result = [-result[1], result[0] + result[1]];
    return result;
  }

  function footprint(part) {
    if (part.type === "track") {
      const raw = part.trackHexes || [];
      const includesOrigin = raw.some(([q, r]) => q === 0 && r === 0);
      return includesOrigin ? raw : [[0, 0], ...raw];
    }
    const base = FOOTPRINTS[part.type] || [[0, 0]];
    return base.map((cell) => rotateCell(cell, part.rotation || 0));
  }

  function occupiedCells(part) {
    const origin = part.position || [0, 0];
    return footprint(part).map((cell) => add(origin, cell));
  }

  function direction(rotation = 0) {
    return DIRECTIONS[((Number(rotation) % 6) + 6) % 6];
  }

  function label(type = "") {
    return LABELS[type] || type.replace("glyph-", "").split(/[-_]/).map((part) => part[0] || "").join("").slice(0, 3).toUpperCase();
  }

  window.OpusGeometry = { DIRECTIONS, FOOTPRINTS, add, rotateCell, footprint, occupiedCells, direction, label };
})();