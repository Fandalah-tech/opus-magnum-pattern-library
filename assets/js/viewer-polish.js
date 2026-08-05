(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root || !window.OpusSolutionViewer) return;

  const { axialToPixel, svgEl } = window.OpusSolutionViewer.constants;
  const SIZE = 34;
  const ATOM_LABELS = {
    salt: 'S', air: 'A', earth: 'E', fire: 'F', water: 'W',
    quicksilver: 'Q', gold: 'Au', silver: 'Ag', copper: 'Cu', iron: 'Fe',
    tin: 'Sn', lead: 'Pb', vitae: 'V', mors: 'M', quintessence: 'Qe', repeat: 'R'
  };

  let viewer = null;
  let atomLabelLayer = null;
  let previousAtomPositions = new Map();
  let atomAnimationFrame = null;
  const armLabelFrames = new Map();

  function hexPoints(x, y, radius = SIZE * .86) {
    return Array.from({ length: 6 }, (_, index) => {
      const angle = Math.PI / 180 * (60 * index - 30);
      return `${x + radius * Math.cos(angle)},${y + radius * Math.sin(angle)}`;
    }).join(' ');
  }

  function reorderDynamicLayers() {
    const world = viewer?.world || root.querySelector('[data-viewer-world]');
    if (!world) return;
    const arm = world.querySelector('[data-viewer-layer="arm"]');
    const bond = world.querySelector('[data-viewer-layer="bond"]');
    const atom = world.querySelector('[data-viewer-layer="atom"]');
    const overlay = world.querySelector('[data-viewer-layer="overlay"]');
    if (arm && bond) world.insertBefore(arm, bond);
    if (bond && atom) world.insertBefore(bond, atom);
    const delivery = world.querySelector('[data-viewer-layer="delivery"]');
    if (delivery && overlay) world.insertBefore(delivery, overlay);
  }

  function ensureAtomLabelLayer() {
    if (atomLabelLayer?.isConnected) return atomLabelLayer;
    const world = viewer?.world || root.querySelector('[data-viewer-world]');
    if (!world) return null;
    atomLabelLayer = svgEl('g', {
      class: 'viewer-layer viewer-layer-atom-labels',
      'data-viewer-layer': 'atom-labels',
      'pointer-events': 'none'
    });
    const overlay = world.querySelector('[data-viewer-layer="overlay"]');
    world.insertBefore(atomLabelLayer, overlay || null);
    return atomLabelLayer;
  }

  function allAtoms(frame) {
    return (frame?.molecules || []).flatMap((molecule) =>
      (molecule.atoms || []).map((atom) => ({
        ...atom,
        moleculeHeld: Array.isArray(molecule.heldBy) && molecule.heldBy.length > 0
      }))
    );
  }

  function drawAtomLabels(atoms, t) {
    const layer = ensureAtomLabelLayer();
    if (!layer) return;
    layer.replaceChildren();
    for (const atom of atoms) {
      const start = previousAtomPositions.get(String(atom.id)) || atom.position || [0, 0];
      const end = atom.position || start;
      const [sx, sy] = axialToPixel(start);
      const [ex, ey] = axialToPixel(end);
      const x = sx + (ex - sx) * t;
      const y = sy + (ey - sy) * t;
      const label = ATOM_LABELS[atom.element] || String(atom.element || '?').slice(0, 2).toUpperCase();
      const text = svgEl('text', {
        x,
        y: y + 4.1,
        'text-anchor': 'middle',
        fill: atom.element === 'salt' ? '#4d463c' : '#17120e',
        stroke: atom.moleculeHeld ? '#fff1ad' : '#fff8e7',
        'stroke-width': atom.moleculeHeld ? .75 : .45,
        'paint-order': 'stroke',
        'font-size': label.length > 1 ? 7.8 : 9.5,
        'font-weight': 900,
        'font-family': 'ui-sans-serif,system-ui,sans-serif',
        class: `viewer-atom-symbol${atom.moleculeHeld ? ' held' : ''}`
      });
      text.textContent = label;
      layer.append(text);
    }
  }

  function animateAtomLabels(frame, duration) {
    if (atomAnimationFrame) cancelAnimationFrame(atomAnimationFrame);
    const atoms = allAtoms(frame);
    const started = performance.now();
    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - raw, 3);
      drawAtomLabels(atoms, eased);
      if (raw < 1) atomAnimationFrame = requestAnimationFrame(tick);
      else {
        atomAnimationFrame = null;
        previousAtomPositions = new Map(atoms.map((atom) => [String(atom.id), [...(atom.position || [0, 0])]]));
      }
    };
    atomAnimationFrame = requestAnimationFrame(tick);
  }

  function installFullHexHitTargets(solution) {
    for (const part of solution?.parts || []) {
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (!group || group.querySelector('[data-part-hit-targets]')) continue;
      const hits = svgEl('g', {
        'data-part-hit-targets': String(part.id),
        class: 'viewer-part-hit-targets'
      });
      for (const cell of window.OpusGeometry?.occupiedCells(part) || [part.position || [0, 0]]) {
        const [x, y] = axialToPixel(cell);
        hits.append(svgEl('polygon', {
          points: hexPoints(x, y),
          fill: '#fff',
          'fill-opacity': .001,
          stroke: 'none',
          'pointer-events': 'all',
          class: 'viewer-part-hit-target'
        }));
      }
      group.prepend(hits);
    }
  }

  function armNumber(part) {
    const raw = Number(part.armNumber ?? 0);
    return Number.isFinite(raw) ? raw + 1 : 1;
  }

  function installArmLabels(solution) {
    for (const part of solution?.parts || []) {
      if (!/^(arm|piston|baron)/.test(String(part.type || ''))) continue;
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (!group) continue;

      const decorativeHub = group.querySelector(':scope > circle:last-of-type');
      if (decorativeHub) {
        decorativeHub.setAttribute('opacity', '0');
        decorativeHub.setAttribute('data-arm-hub-decoration', 'hidden');
      }

      if (group.querySelector('[data-arm-number-label]')) continue;
      const [x, y] = axialToPixel(part.position || [0, 0]);
      const label = svgEl('text', {
        x,
        y: y + 5,
        'text-anchor': 'middle',
        fill: '#fff1ca',
        stroke: '#17110b',
        'stroke-width': 3.2,
        'paint-order': 'stroke',
        'font-size': 14,
        'font-weight': 950,
        'font-family': 'ui-sans-serif,system-ui,sans-serif',
        'data-arm-number-label': String(part.id),
        'pointer-events': 'none'
      });
      label.textContent = String(armNumber(part));
      group.append(label);
    }
  }

  function moveArmLabel(state, duration) {
    const label = root.querySelector(`[data-arm-number-label="${CSS.escape(String(state.partId))}"]`);
    if (!label) return;
    const previous = armLabelFrames.get(String(state.partId));
    if (previous) cancelAnimationFrame(previous);
    const [tx, ty] = axialToPixel(state.origin || [0, 0]);
    const sx = Number(label.getAttribute('x')) || tx;
    const sy = (Number(label.getAttribute('y')) || (ty + 5)) - 5;
    const started = performance.now();
    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const t = 1 - Math.pow(1 - raw, 3);
      label.setAttribute('x', sx + (tx - sx) * t);
      label.setAttribute('y', sy + (ty - sy) * t + 5);
      if (raw < 1) armLabelFrames.set(String(state.partId), requestAnimationFrame(tick));
      else armLabelFrames.delete(String(state.partId));
    };
    armLabelFrames.set(String(state.partId), requestAnimationFrame(tick));
  }

  function contentBounds() {
    const names = ['track', 'glyph', 'part', 'arm', 'bond', 'atom', 'atom-labels', 'delivery'];
    const boxes = names.map((name) => viewer?.world?.querySelector(`[data-viewer-layer="${name}"]`))
      .filter(Boolean)
      .map((node) => {
        try { return node.getBBox(); } catch { return null; }
      })
      .filter((box) => box && box.width >= 0 && box.height >= 0 && (box.width || box.height));
    if (!boxes.length) return null;
    const minX = Math.min(...boxes.map((box) => box.x));
    const minY = Math.min(...boxes.map((box) => box.y));
    const maxX = Math.max(...boxes.map((box) => box.x + box.width));
    const maxY = Math.max(...boxes.map((box) => box.y + box.height));
    return { x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
  }

  function installContentFit() {
    if (!viewer || viewer.__contentFitInstalled) return;
    viewer.__contentFitInstalled = true;
    viewer.fit = () => {
      const box = contentBounds();
      if (!box) return;
      const width = viewer.svg.clientWidth || 900;
      const height = viewer.svg.clientHeight || 560;
      const padding = Math.max(58, Math.min(width, height) * .11);
      viewer.scale = Math.max(.28, Math.min(2.15, Math.min(
        (width - padding * 2) / box.width,
        (height - padding * 2) / box.height
      )));
      viewer.tx = width / 2 - (box.x + box.width / 2) * viewer.scale;
      viewer.ty = height / 2 - (box.y + box.height / 2) * viewer.scale;
      viewer.applyTransform();
    };
  }

  function fitAfterLayout() {
    requestAnimationFrame(() => requestAnimationFrame(() => viewer?.fit?.()));
  }

  window.addEventListener('opus:analysisready', (event) => {
    viewer = event.detail?.viewer || viewer;
    atomLabelLayer = null;
    previousAtomPositions = new Map();
    reorderDynamicLayers();
    ensureAtomLabelLayer();
    installFullHexHitTargets(event.detail?.payload?.solution);
    installArmLabels(event.detail?.payload?.solution);
    installContentFit();
    window.__OPUS_VIEWER_FIT_CONTENT__ = () => viewer?.fit?.();
    fitAfterLayout();
    window.setTimeout(fitAfterLayout, 180);
  });

  root.addEventListener('opus:replayframe', (event) => {
    reorderDynamicLayers();
    const duration = Number(event.detail?.animationDuration ?? 160);
    animateAtomLabels(event.detail?.frame, duration);
    for (const state of event.detail?.frame?.armStates || []) moveArmLabel(state, duration);
  });
})();
