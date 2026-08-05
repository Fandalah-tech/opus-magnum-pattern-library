(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const world = root.querySelector('[data-viewer-world]');
  if (!world) return;

  const NS = 'http://www.w3.org/2000/svg';
  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const COLORS = {
    salt: '#f0eee5', air: '#9ed9e8', earth: '#8f7149', fire: '#e66c4d', water: '#5ea9d6',
    quicksilver: '#b9c0c9', gold: '#d8ae45', silver: '#c4ccd4', copper: '#b87445', iron: '#777b80',
    tin: '#aeb3b4', lead: '#6f6578', vitae: '#f0d46a', mors: '#a48bb9', quintessence: '#e8c2ff',
    repeat: '#d7d7d7'
  };

  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };

  let bondLayer = null;
  let atomLayer = null;
  let previousMolecules = new Map();
  let animationFrame = null;

  function ensureLayers() {
    bondLayer = world.querySelector('[data-viewer-layer="bond"]') || bondLayer;
    atomLayer = world.querySelector('[data-viewer-layer="atom"]') || atomLayer;
    if (!bondLayer?.isConnected) {
      bondLayer = svgEl('g', { class: 'viewer-layer viewer-layer-bond replay-bond-layer', 'data-viewer-layer': 'bond' });
      world.append(bondLayer);
    }
    if (!atomLayer?.isConnected) {
      atomLayer = svgEl('g', { class: 'viewer-layer viewer-layer-atom replay-atom-layer', 'data-viewer-layer': 'atom' });
      world.append(atomLayer);
    }
    return { bondLayer, atomLayer };
  }

  function cloneMolecule(molecule) {
    return {
      ...molecule,
      atoms: (molecule.atoms || []).map((atom) => ({ ...atom, position: [...atom.position] })),
      bonds: (molecule.bonds || []).map((bond) => ({ ...bond, from: [...bond.from], to: [...bond.to] }))
    };
  }

  function interpolatePosition(start, end, t) {
    const [sx, sy] = axialToPixel(start || end || [0, 0]);
    const [ex, ey] = axialToPixel(end || start || [0, 0]);
    return [sx + (ex - sx) * t, sy + (ey - sy) * t];
  }

  function moleculeHeld(molecule) {
    return Array.isArray(molecule.heldBy) ? molecule.heldBy.length > 0 : Boolean(molecule.heldBy);
  }

  function dispatchSelection(kind, atom, molecule) {
    root.dispatchEvent(new CustomEvent('opus:viewerselect', {
      bubbles: true,
      detail: { kind, atom, molecule }
    }));
  }

  function drawInterpolated(molecules, t) {
    const layers = ensureLayers();
    layers.bondLayer.replaceChildren();
    layers.atomLayer.replaceChildren();

    for (const molecule of molecules || []) {
      const previous = previousMolecules.get(molecule.id);
      const held = moleculeHeld(molecule);
      const previousAtoms = new Map((previous?.atoms || []).map((atom) => [atom.id, atom]));
      const previousBonds = new Map((previous?.bonds || []).map((bond) => [bond.id, bond]));

      const bondGroup = svgEl('g', {
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
        const [x1, y1] = interpolatePosition(oldBond?.from, bond.from, t);
        const [x2, y2] = interpolatePosition(oldBond?.to, bond.to, t);
        bondGroup.append(svgEl('line', {
          x1, y1, x2, y2,
          stroke: '#211d18',
          'stroke-width': bond.type === 'triplex' ? 12 : 9,
          'stroke-linecap': 'round',
          opacity: .95,
          class: 'replay-bond-shadow'
        }));
        bondGroup.append(svgEl('line', {
          x1, y1, x2, y2,
          stroke: bond.type === 'triplex' ? '#f0c56f' : '#e8dcc4',
          'stroke-width': bond.type === 'triplex' ? 7 : 4.5,
          'stroke-linecap': 'round',
          opacity: .95,
          class: `replay-bond replay-bond-${bond.type || 'normal'}`
        }));
      }
      layers.bondLayer.append(bondGroup);

      const atomGroup = svgEl('g', {
        class: `replay-molecule-atoms${held ? ' held' : ''}`,
        'data-molecule-id': molecule.id
      });
      for (const atom of molecule.atoms || []) {
        const oldAtom = previousAtoms.get(atom.id);
        const [x, y] = interpolatePosition(oldAtom?.position, atom.position, t);
        const atomNode = svgEl('g', {
          class: `replay-atom replay-atom-${atom.element}${held ? ' held' : ''}`,
          'data-atom-id': atom.id,
          'data-molecule-id': molecule.id,
          tabindex: 0,
          role: 'button',
          'aria-label': `${atom.element} atom ${atom.id}`
        });
        atomNode.append(svgEl('circle', {
          cx: x, cy: y, r: 16.5,
          fill: '#14110e',
          stroke: held ? '#f7d97f' : '#393027',
          'stroke-width': held ? 4 : 3,
          opacity: .98,
          class: 'replay-atom-ring'
        }));
        atomNode.append(svgEl('circle', {
          cx: x, cy: y, r: 12.5,
          fill: COLORS[atom.element] || '#ddd',
          stroke: '#f8f1e3',
          'stroke-opacity': .28,
          'stroke-width': 1.4,
          class: 'replay-atom-core'
        }));
        atomNode.append(svgEl('circle', {
          cx: x - 4, cy: y - 5, r: 3.2,
          fill: '#fff', opacity: .48,
          class: 'replay-atom-highlight'
        }));
        const title = svgEl('title');
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

  function animateMolecules(molecules, duration) {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    const started = performance.now();

    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - raw, 3);
      drawInterpolated(molecules, eased);
      if (raw < 1) animationFrame = requestAnimationFrame(tick);
      else {
        animationFrame = null;
        previousMolecules = new Map((molecules || []).map((molecule) => [molecule.id, cloneMolecule(molecule)]));
      }
    };
    animationFrame = requestAnimationFrame(tick);
  }

  root.addEventListener('opus:replayframe', (event) => {
    const molecules = event.detail.frame?.molecules || [];
    const playing = root.querySelector('[data-replay-play]')?.dataset.state === 'playing';
    animateMolecules(molecules, playing ? 420 : 140);
  });

  window.addEventListener('opus:analysisready', () => {
    previousMolecules = new Map();
    if (animationFrame) cancelAnimationFrame(animationFrame);
    animationFrame = null;
    ensureLayers();
  });
})();