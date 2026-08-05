(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root || !window.OpusGeometry || !window.OpusSolutionViewer) return;

  const { SIZE, hexPoints, axialToPixel, svgEl } = window.OpusSolutionViewer.constants;
  let viewer = null;
  let replay = null;
  let cumulativeByFrame = [];
  let activeByFrame = [];
  let areaLayer = null;
  let badge = null;

  const key = ([q, r]) => `${Number(q)},${Number(r)}`;
  const cell = (value) => value.split(',').map(Number);

  function staticCells(solution) {
    const result = new Set();
    for (const part of solution?.parts || []) {
      for (const position of window.OpusGeometry.occupiedCells(part)) result.add(key(position));
    }
    return result;
  }

  function activeCells(frame) {
    const result = new Set();
    for (const molecule of frame?.molecules || []) {
      for (const atom of molecule.atoms || []) result.add(key(atom.position || [0, 0]));
    }
    for (const arm of frame?.armStates || []) {
      result.add(key(arm.origin || [0, 0]));
      for (const tip of arm.tips || []) result.add(key(tip.position || arm.origin || [0, 0]));
    }
    return result;
  }

  function ensureLayer() {
    if (areaLayer?.isConnected) return areaLayer;
    const world = viewer?.world || root.querySelector('[data-viewer-world]');
    if (!world) return null;
    areaLayer = svgEl('g', {
      class: 'viewer-layer viewer-layer-area',
      'data-viewer-layer': 'area',
      'pointer-events': 'none'
    });
    const trackLayer = world.querySelector('[data-viewer-layer="track"]');
    world.insertBefore(areaLayer, trackLayer || world.firstChild?.nextSibling || null);
    return areaLayer;
  }

  function ensureBadge() {
    if (badge?.isConnected) return badge;
    const canvas = root.querySelector('.viewer-canvas');
    if (!canvas) return null;
    badge = document.createElement('div');
    badge.className = 'viewer-area-badge';
    badge.setAttribute('aria-live', 'polite');
    canvas.append(badge);
    return badge;
  }

  function build(payload) {
    replay = payload?.replay || null;
    const frames = replay?.frames || [];
    const used = staticCells(payload?.solution);
    cumulativeByFrame = [];
    activeByFrame = [];

    for (const frame of frames) {
      const active = activeCells(frame);
      for (const position of active) used.add(position);
      activeByFrame.push(new Set(active));
      cumulativeByFrame.push(new Set(used));
    }

    window.__OPUS_USED_AREA__ = {
      cumulativeByFrame: cumulativeByFrame.map((set) => [...set].map(cell)),
      activeByFrame: activeByFrame.map((set) => [...set].map(cell))
    };
  }

  function render(frame, trace) {
    const layer = ensureLayer();
    if (!layer || !trace?.frames?.length) return;
    const index = Math.max(0, trace.frames.indexOf(frame));
    const used = cumulativeByFrame[index] || new Set();
    const active = activeByFrame[index] || new Set();
    layer.replaceChildren();

    for (const positionKey of used) {
      const [q, r] = cell(positionKey);
      const [x, y] = axialToPixel([q, r]);
      const isActive = active.has(positionKey);
      layer.append(svgEl('polygon', {
        points: hexPoints(x, y, SIZE * .87),
        fill: isActive ? '#c08a3d' : '#82572b',
        'fill-opacity': isActive ? .38 : .23,
        stroke: isActive ? '#e0b56e' : '#a3723e',
        'stroke-opacity': isActive ? .68 : .38,
        'stroke-width': isActive ? 1.45 : .95,
        class: isActive ? 'viewer-area-cell active' : 'viewer-area-cell used'
      }));
    }

    const node = ensureBadge();
    if (node) node.textContent = `Used area · ${used.size} hexes · ${active.size} active`;
  }

  window.addEventListener('opus:analysisready', (event) => {
    viewer = event.detail?.viewer || viewer;
    areaLayer = null;
    badge?.remove();
    badge = null;
    build(event.detail?.payload);
    ensureLayer();
    ensureBadge();
  });

  root.addEventListener('opus:replayframe', (event) => {
    render(event.detail?.frame, event.detail?.trace || replay);
  });
})();
