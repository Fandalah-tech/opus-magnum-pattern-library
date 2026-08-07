(() => {
  if (window.OpusSceneDiff) return;

  const hexKey = value => `${Number(value?.[0] || 0)},${Number(value?.[1] || 0)}`;
  const sameHex = (a, b) => hexKey(a) === hexKey(b);
  const stable = value => JSON.stringify(value, Object.keys(value || {}).sort());

  function partSignature(part) {
    return [
      String(part?.type || ''),
      Number(part?.which ?? -1),
      Number(part?.armNumber ?? -1)
    ].join('|');
  }

  function indexParts(scene) {
    const byId = new Map();
    const bySignature = new Map();
    for (const part of scene?.static?.parts || []) {
      byId.set(String(part.id), part);
      const signature = partSignature(part);
      if (!bySignature.has(signature)) bySignature.set(signature, []);
      bySignature.get(signature).push(part);
    }
    return { byId, bySignature };
  }

  function comparablePart(part) {
    return {
      type: part?.type || null,
      rotation: Number(part?.rotation || 0),
      length: Number(part?.length || 0),
      which: Number(part?.which ?? -1),
      armNumber: Number(part?.armNumber ?? -1),
      trackHexes: (part?.trackHexes || []).map(hexKey),
      program: (part?.program || []).map(item => ({ ...item }))
    };
  }

  function comparePart(before, after) {
    const moved = !sameHex(before?.position, after?.position);
    const beforeComparable = comparablePart(before);
    const afterComparable = comparablePart(after);
    const changed = stable(beforeComparable) !== stable(afterComparable);
    return {
      before,
      after,
      moved,
      changed,
      from: [...(before?.position || [0, 0])],
      to: [...(after?.position || [0, 0])]
    };
  }

  function pairParts(beforeScene, afterScene) {
    const beforeIndex = indexParts(beforeScene);
    const afterIndex = indexParts(afterScene);
    const usedAfter = new Set();
    const pairs = [];
    const removed = [];

    for (const before of beforeScene?.static?.parts || []) {
      let after = afterIndex.byId.get(String(before.id));
      if (after && usedAfter.has(String(after.id))) after = null;
      if (!after) {
        const candidates = afterIndex.bySignature.get(partSignature(before)) || [];
        after = candidates.find(candidate => !usedAfter.has(String(candidate.id))) || null;
      }
      if (!after) {
        removed.push(before);
        continue;
      }
      usedAfter.add(String(after.id));
      pairs.push(comparePart(before, after));
    }

    const added = (afterScene?.static?.parts || []).filter(part => !usedAfter.has(String(part.id)));
    return { pairs, added, removed };
  }

  function metricDelta(beforeScene, afterScene) {
    const before = beforeScene?.meta?.metrics || {};
    const after = afterScene?.meta?.metrics || {};
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    const result = {};
    for (const key of keys) {
      const a = Number(before[key]);
      const b = Number(after[key]);
      if (Number.isFinite(a) || Number.isFinite(b)) {
        result[key] = {
          before: Number.isFinite(a) ? a : null,
          after: Number.isFinite(b) ? b : null,
          delta: Number.isFinite(a) && Number.isFinite(b) ? b - a : null
        };
      }
    }
    return result;
  }

  function occupancyDelta(beforeScene, afterScene) {
    const before = new Map((beforeScene?.static?.occupiedCells || []).map(cell => [hexKey(cell), [...cell]]));
    const after = new Map((afterScene?.static?.occupiedCells || []).map(cell => [hexKey(cell), [...cell]]));
    return {
      added: [...after.entries()].filter(([key]) => !before.has(key)).map(([, cell]) => cell),
      removed: [...before.entries()].filter(([key]) => !after.has(key)).map(([, cell]) => cell),
      shared: [...after.entries()].filter(([key]) => before.has(key)).map(([, cell]) => cell)
    };
  }

  function diff(beforeScene, afterScene) {
    if (beforeScene?.kind !== 'opus-scene' || afterScene?.kind !== 'opus-scene') {
      throw new Error('OpusSceneDiff.diff requires two Opus scenes');
    }
    const { pairs, added, removed } = pairParts(beforeScene, afterScene);
    const moved = pairs.filter(item => item.moved);
    const changed = pairs.filter(item => item.changed);
    const unchanged = pairs.filter(item => !item.moved && !item.changed);
    const occupancy = occupancyDelta(beforeScene, afterScene);
    return {
      kind: 'opus-scene-diff',
      schemaVersion: '0.1.0',
      before: beforeScene,
      after: afterScene,
      parts: { added, removed, moved, changed, unchanged, pairs },
      occupancy,
      metrics: metricDelta(beforeScene, afterScene),
      summary: {
        addedParts: added.length,
        removedParts: removed.length,
        movedParts: moved.length,
        changedParts: changed.length,
        unchangedParts: unchanged.length,
        addedCells: occupancy.added.length,
        removedCells: occupancy.removed.length
      }
    };
  }

  window.OpusSceneDiff = Object.freeze({ diff, partSignature });
})();
