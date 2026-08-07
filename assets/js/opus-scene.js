(() => {
  if (window.OpusScene) return;
  const GEO = window.OpusGeometry;
  const CORE = window.OpusRendererCore;
  if (!GEO || !CORE) throw new Error('OpusGeometry and OpusRendererCore must load before opus-scene.js');

  const cloneHex = value => Array.isArray(value) ? [Number(value[0] || 0), Number(value[1] || 0)] : [0, 0];
  const clonePart = part => ({
    ...part,
    position: cloneHex(part?.position),
    trackHexes: (part?.trackHexes || []).map(cloneHex),
    program: (part?.program || []).map(item => ({ ...item }))
  });

  function indexRelations(graph) {
    const relations = new Map();
    for (const edge of graph?.edges || []) {
      if (!relations.has(edge.source)) relations.set(edge.source, new Set());
      if (!relations.has(edge.target)) relations.set(edge.target, new Set());
      relations.get(edge.source).add(edge.target);
      relations.get(edge.target).add(edge.source);
    }
    return relations;
  }

  function normalizeFrame(frame, index) {
    if (!frame) return null;
    return {
      index,
      cycle: Number(frame.cycle ?? -1),
      displayCycle: Number(frame.displayCycle ?? Math.max(0, Number(frame.cycle ?? -1) + 1)),
      phaseLabel: frame.phaseLabel || null,
      events: (frame.events || []).map(event => ({ ...event })),
      arms: (frame.armStates || []).map(state => ({
        ...state,
        origin: cloneHex(state.origin),
        tips: (state.tips || []).map((tip, branchIndex) => ({
          ...tip,
          branchIndex: Number(tip.branchIndex ?? branchIndex),
          position: cloneHex(tip.position)
        })),
        heldMoleculeIds: [...(state.heldMoleculeIds || [])]
      })),
      molecules: (frame.molecules || []).map(molecule => ({
        ...molecule,
        heldBy: [...(molecule.heldBy || [])],
        atoms: (molecule.atoms || []).map(atom => ({ ...atom, position: cloneHex(atom.position) })),
        bonds: (molecule.bonds || []).map(bond => ({
          ...bond,
          from: cloneHex(bond.from),
          to: cloneHex(bond.to)
        }))
      }))
    };
  }

  function build(payload, options = {}) {
    if (!payload?.solution) throw new Error('Cannot build an Opus scene without a solution');
    const solution = payload.solution;
    const graph = payload.graph || { nodes: [], edges: [] };
    const parts = (solution.parts || []).map(clonePart).map(part => ({
      ...part,
      kind: CORE.partKind(part.type),
      occupiedCells: GEO.occupiedCells(part).map(cloneHex),
      armTips: CORE.partKind(part.type) === 'arm' ? CORE.armTips(part).map(tip => ({ ...tip, position: cloneHex(tip.position) })) : []
    }));
    const occupiedCells = parts.flatMap(part => part.occupiedCells.map(cloneHex));
    const relations = indexRelations(graph);
    const frames = (payload.replay?.frames || []).map(normalizeFrame);
    const requestedFrame = Number(options.frameIndex ?? 0);
    const frameIndex = frames.length ? Math.max(0, Math.min(frames.length - 1, requestedFrame)) : -1;

    return {
      schemaVersion: '0.1.0',
      kind: 'opus-scene',
      source: {
        puzzle: payload.puzzle || null,
        solution,
        graph,
        validation: payload.validation || null,
        replay: payload.replay || null
      },
      meta: {
        puzzleName: payload.puzzle?.name || solution.puzzleFile || 'Puzzle',
        solutionName: solution.name || solution.source?.name || 'Solution',
        metrics: { ...(solution.metrics || {}), ...(payload.validation?.metrics || {}) },
        validationStatus: payload.validation?.status || (payload.validation?.valid === true ? 'valid' : payload.validation?.valid === false ? 'invalid' : 'unknown')
      },
      static: {
        parts,
        occupiedCells,
        graph,
        relations
      },
      timeline: {
        frames,
        frameIndex,
        frame: frameIndex >= 0 ? frames[frameIndex] : null,
        cycleCount: Number(payload.replay?.summary?.cycleCount ?? Math.max(0, frames.length - 1))
      }
    };
  }

  function atFrame(scene, frameIndex) {
    if (!scene?.timeline?.frames) return scene;
    const frames = scene.timeline.frames;
    const index = frames.length ? Math.max(0, Math.min(frames.length - 1, Number(frameIndex || 0))) : -1;
    return {
      ...scene,
      timeline: {
        ...scene.timeline,
        frameIndex: index,
        frame: index >= 0 ? frames[index] : null
      }
    };
  }

  function related(scene, partId) {
    return new Set(scene?.static?.relations?.get(partId) || []);
  }

  window.OpusScene = Object.freeze({ build, atFrame, related });
})();
