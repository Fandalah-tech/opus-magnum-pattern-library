(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const world = root.querySelector('[data-viewer-world]');
  if (!world) return;
  const core = window.OpusRendererCore;
  if (!core) throw new Error('OpusRendererCore must load before replay-molecules.js');

  let bondLayer = null;
  let atomLayer = null;
  let previousAtoms = new Map();
  let previousBonds = new Map();
  let animationFrame = null;

  function ensureLayers() {
    bondLayer = world.querySelector('[data-viewer-layer="bond"]') || bondLayer;
    atomLayer = world.querySelector('[data-viewer-layer="atom"]') || atomLayer;
    if (!bondLayer?.isConnected) {
      bondLayer = core.svgEl('g', { class: 'viewer-layer viewer-layer-bond replay-bond-layer', 'data-viewer-layer': 'bond' });
      world.append(bondLayer);
    }
    if (!atomLayer?.isConnected) {
      atomLayer = core.svgEl('g', { class: 'viewer-layer viewer-layer-atom replay-atom-layer', 'data-viewer-layer': 'atom' });
      world.append(atomLayer);
    }
    return { bondLayer, atomLayer };
  }

  function cloneAtom(atom) {
    return { ...atom, position: [...(atom.position || [0, 0])] };
  }

  function cloneBond(bond) {
    return { ...bond, from: [...(bond.from || [0, 0])], to: [...(bond.to || [0, 0])] };
  }

  function moleculeHeld(molecule) {
    return Array.isArray(molecule.heldBy) ? molecule.heldBy.length > 0 : Boolean(molecule.heldBy);
  }

  function dispatchSelection(kind, atom, molecule) {
    root.dispatchEvent(new CustomEvent('opus:viewerselect', { bubbles: true, detail: { kind, atom, molecule } }));
  }

  function drawInterpolated(molecules, t) {
    const layers = ensureLayers();
    layers.bondLayer.replaceChildren();
    layers.atomLayer.replaceChildren();

    for (const molecule of molecules || []) {
      const held = moleculeHeld(molecule);
      const bondGroup = core.svgEl('g', {
        class: `replay-molecule-bonds${held ? ' held' : ''}`,
        'data-molecule-id': molecule.id,
        'pointer-events': 'stroke'
      });
      bondGroup.addEventListener('click', (event) => {
        event.stopPropagation();
        dispatchSelection('molecule', null, molecule);
      });

      for (const bond of molecule.bonds || []) {
        const oldBond = previousBonds.get(bond.id);
        const [x1, y1] = core.interpolateHex(oldBond?.from, bond.from, t);
        const [x2, y2] = core.interpolateHex(oldBond?.to, bond.to, t);
        bondGroup.append(core.svgEl('line', {
          x1, y1, x2, y2, stroke: '#211d18',
          'stroke-width': bond.type === 'triplex' ? 12 : 9,
          'stroke-linecap': 'round', opacity: .95, class: 'replay-bond-shadow'
        }));
        bondGroup.append(core.svgEl('line', {
          x1, y1, x2, y2,
          stroke: bond.type === 'triplex' ? '#f0c56f' : '#e8dcc4',
          'stroke-width': bond.type === 'triplex' ? 7 : 4.5,
          'stroke-linecap': 'round', opacity: .95,
          class: `replay-bond replay-bond-${bond.type || 'normal'}`
        }));
      }
      layers.bondLayer.append(bondGroup);

      const atomGroup = core.svgEl('g', {
        class: `replay-molecule-atoms${held ? ' held' : ''}`,
        'data-molecule-id': molecule.id
      });
      for (const atom of molecule.atoms || []) {
        const oldAtom = previousAtoms.get(atom.id);
        const [x, y] = core.interpolateHex(oldAtom?.position, atom.position, t);
        const transformed = oldAtom && oldAtom.element !== atom.element;
        const atomNode = core.svgEl('g', {
          class: `replay-atom replay-atom-${atom.element}${held ? ' held' : ''}${transformed ? ' transformed' : ''}`,
          'data-atom-id': atom.id,
          'data-molecule-id': molecule.id,
          'data-element': atom.element,
          tabindex: 0,
          role: 'button',
          'aria-label': `${atom.element} atom ${atom.id}`
        });
        atomNode.append(core.svgEl('circle', {
          cx: x, cy: y, r: 16.5,
          fill: '#14110e',
          stroke: transformed ? '#fff1a9' : held ? '#f7d97f' : '#393027',
          'stroke-width': transformed || held ? 4 : 3,
          opacity: .98,
          class: 'replay-atom-ring'
        }));
        atomNode.append(core.svgEl('circle', {
          cx: x, cy: y, r: 12.5,
          fill: core.ELEMENT_COLORS[atom.element] || '#ddd',
          stroke: '#f8f1e3',
          'stroke-opacity': .28,
          'stroke-width': 1.4,
          class: 'replay-atom-core'
        }));
        atomNode.append(core.svgEl('circle', {
          cx: x - 4, cy: y - 5, r: 3.2,
          fill: '#fff', opacity: .48,
          class: 'replay-atom-highlight'
        }));
        const title = core.svgEl('title');
        title.textContent = `${atom.element} · ${molecule.id}`;
        atomNode.append(title);
        atomNode.addEventListener('click', (event) => {
          event.stopPropagation();
          dispatchSelection('atom', atom, molecule);
        });
        atomNode.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            dispatchSelection('atom', atom, molecule);
          }
        });
        atomGroup.append(atomNode);
      }
      layers.atomLayer.append(atomGroup);
    }
  }

  function rememberFrame(molecules) {
    previousAtoms = new Map();
    previousBonds = new Map();
    for (const molecule of molecules || []) {
      for (const atom of molecule.atoms || []) previousAtoms.set(atom.id, cloneAtom(atom));
      for (const bond of molecule.bonds || []) previousBonds.set(bond.id, cloneBond(bond));
    }
  }

  function animateMolecules(molecules, duration) {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    const started = performance.now();
    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      drawInterpolated(molecules, core.easeOutCubic(raw));
      if (raw < 1) animationFrame = requestAnimationFrame(tick);
      else {
        animationFrame = null;
        rememberFrame(molecules);
      }
    };
    animationFrame = requestAnimationFrame(tick);
  }

  root.addEventListener('opus:replayframe', (event) => {
    const frame = event.detail?.scene?.timeline?.frame || event.detail?.frame || null;
    const molecules = frame?.molecules || [];
    const duration = Number(event.detail?.animationDuration ?? 140);
    animateMolecules(molecules, duration);
  });

  window.addEventListener('opus:analysisready', () => {
    previousAtoms = new Map();
    previousBonds = new Map();
    if (animationFrame) cancelAnimationFrame(animationFrame);
    animationFrame = null;
    ensureLayers();
  });
})();
