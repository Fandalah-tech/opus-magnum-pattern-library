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

  let layer = null;
  function ensureLayer() {
    if (layer?.isConnected) return layer;
    layer = svgEl('g', { class: 'replay-molecule-layer', 'pointer-events': 'none' });
    world.append(layer);
    return layer;
  }

  function drawMolecules(molecules) {
    const target = ensureLayer();
    target.replaceChildren();
    for (const molecule of molecules || []) {
      const group = svgEl('g', {
        class: `replay-molecule${molecule.heldBy ? ' held' : ''}`,
        'data-molecule-id': molecule.id,
        'data-held-by': molecule.heldBy || ''
      });
      for (const bond of molecule.bonds || []) {
        const [x1, y1] = axialToPixel(bond.from);
        const [x2, y2] = axialToPixel(bond.to);
        group.append(svgEl('line', {
          x1, y1, x2, y2,
          stroke: '#e8dcc4',
          'stroke-width': bond.type === 'triplex' ? 9 : 6,
          'stroke-linecap': 'round',
          opacity: .85
        }));
      }
      for (const atom of molecule.atoms || []) {
        const [x, y] = axialToPixel(atom.position);
        group.append(svgEl('circle', {
          cx: x, cy: y, r: 13,
          fill: COLORS[atom.element] || '#ddd',
          stroke: molecule.heldBy ? '#fff2a8' : '#201d19',
          'stroke-width': molecule.heldBy ? 4 : 3
        }));
        const title = svgEl('title');
        title.textContent = `${atom.element} · ${molecule.id}`;
        group.append(title);
      }
      target.append(group);
    }
  }

  root.addEventListener('opus:replayframe', (event) => {
    drawMolecules(event.detail.frame?.molecules || []);
  });
})();
