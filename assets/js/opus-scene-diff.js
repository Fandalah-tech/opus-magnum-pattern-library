(() => {
  if (window.OpusSceneDiff) return;

  const hexKey = value => `${Number(value?.[0] || 0)},${Number(value?.[1] || 0)}`;
  const sameHex = (a, b) => hexKey(a) === hexKey(b);

  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') {
      return Object.keys(value).sort().reduce((result, key) => {
        result[key] = canonical(value[key]);
        return result;
      }, {});
    }
    return value;
  }

  const stable = value => JSON.stringify(canonical(value));

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

  function hexDistance(a, b) {
    const aq = Number(a?.[0] || 0), ar = Number(a?.[1] || 0);
    const bq = Number(b?.[0] || 0), br = Number(b?.[1] || 0);
    const dq = aq - bq, dr = ar - br;
    return Math.max(Math.abs(dq), Math.abs(dr), Math.abs(dq + dr));
  }

  function pairingCost(before, after) {
    let cost = hexDistance(before?.position, after?.position) * 10;
    if (Number(before?.rotation || 0) !== Number(after?.rotation || 0)) cost += 3;
    if (Number(before?.length || 0) !== Number(after?.length || 0)) cost += 3;
    if (stable(before?.program || []) !== stable(after?.program || [])) cost += 2;
    if (stable((before?.trackHexes || []).map(hexKey)) !== stable((after?.trackHexes || []).map(hexKey))) cost += 2;
    return cost;
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
      pairingCost: pairingCost(before, after),
      from: [...(before?.position || [0, 0])],
      to: [...(after?.position || [0, 0])]
    };
  }

  function matchSignatureGroup(beforeParts, afterParts) {
    const candidates = [];
    for (const before of beforeParts) {
      for (const after of afterParts) {
        candidates.push({
          before,
          after,
          cost: pairingCost(before, after),
          beforeId: String(before.id),
          afterId: String(after.id)
        });
      }
    }
    candidates.sort((a, b) =>
      a.cost - b.cost || a.beforeId.localeCompare(b.beforeId) || a.afterId.localeCompare(b.afterId)
    );

    const usedBefore = new Set();
    const usedAfter = new Set();
    const pairs = [];
    for (const candidate of candidates) {
      if (usedBefore.has(candidate.beforeId) || usedAfter.has(candidate.afterId)) continue;
      usedBefore.add(candidate.beforeId);
      usedAfter.add(candidate.afterId);
      pairs.push(comparePart(candidate.before, candidate.after));
    }
    return { pairs, usedBefore, usedAfter };
  }

  function pairParts(beforeScene, afterScene) {
    const beforeParts = beforeScene?.static?.parts || [];
    const afterParts = afterScene?.static?.parts || [];
    const afterIndex = indexParts(afterScene);
    const usedBefore = new Set();
    const usedAfter = new Set();
    const pairs = [];

    // Stable IDs are trusted only when the semantic signature still matches.
    // Parser-generated ordinal IDs can shift after insertions/removals, so an ID
    // collision across different piece semantics must not force a false pairing.
    for (const before of beforeParts) {
      const after = afterIndex.byId.get(String(before.id));
      if (!after || partSignature(before) !== partSignature(after)) continue;
      usedBefore.add(String(before.id));
      usedAfter.add(String(after.id));
      pairs.push(comparePart(before, after));
    }

    const unmatchedBeforeBySignature = new Map();
    const unmatchedAfterBySignature = new Map();
    for (const before of beforeParts) {
      if (usedBefore.has(String(before.id))) continue;
      const signature = partSignature(before);
      if (!unmatchedBeforeBySignature.has(signature)) unmatchedBeforeBySignature.set(signature, []);
      unmatchedBeforeBySignature.get(signature).push(before);
    }
    for (const after of afterParts) {
      if (usedAfter.has(String(after.id))) continue;
      const signature = partSignature(after);
      if (!unmatchedAfterBySignature.has(signature)) unmatchedAfterBySignature.set(signature, []);
      unmatchedAfterBySignature.get(signature).push(after);
    }

    const signatures = new Set([...unmatchedBeforeBySignature.keys(), ...unmatchedAfterBySignature.keys()]);
    for (const signature of signatures) {
      const beforeGroup = unmatchedBeforeBySignature.get(signature) || [];
      const afterGroup = unmatchedAfterBySignature.get(signature) || [];
      const matched = matchSignatureGroup(beforeGroup, afterGroup);
      pairs.push(...matched.pairs);
      for (const id of matched.usedBefore) usedBefore.add(id);
      for (const id of matched.usedAfter) usedAfter.add(id);
    }

    const removed = beforeParts.filter(part => !usedBefore.has(String(part.id)));
    const added = afterParts.filter(part => !usedAfter.has(String(part.id)));
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

  window.OpusSceneDiff = Object.freeze({ diff, partSignature, pairingCost, hexDistance });
})();
