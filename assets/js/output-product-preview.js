(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root || !window.OpusGeometry) return;

  const NS = 'http://www.w3.org/2000/svg';
  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const COLORS = {
    salt: '#f0eee5', air: '#9ed9e8', earth: '#8f7149', fire: '#e66c4d', water: '#5ea9d6',
    quicksilver: '#b9c0c9', gold: '#d8ae45', silver: '#c4ccd4', copper: '#b87445', iron: '#777b80',
    tin: '#aeb3b4', lead: '#6f6578', vitae: '#f0d46a', mors: '#a48bb9', quintessence: '#e8c2ff',
    repeat: '#d7d7d7'
  };
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };
  const transform = (local, part) => {
    const rotated = window.OpusGeometry.rotateCell(local || [0, 0], Number(part.rotation || 0));
    return window.OpusGeometry.add(part.position || [0, 0], rotated);
  };

  function removeGenericSymbol(group) {
    for (const child of [...group.children]) {
      if (child.tagName.toLowerCase() === 'title') continue;
      if (child.classList.contains('viewer-piece-footprint')) continue;
      child.remove();
    }
  }

  function drawOutputPreview(group, part, product) {
    removeGenericSymbol(group);
    const preview = svgEl('g', {
      class: 'viewer-output-product',
      'data-output-preview': 'true',
      'pointer-events': 'none'
    });
    const atoms = (product?.atoms || [])
      .filter((atom) => atom.element !== 'repeat')
      .map((atom, index) => ({
        id: `preview-atom-${index}`,
        element: atom.element,
        position: transform(atom.position || [0, 0], part)
      }));
    const atomAt = new Map(atoms.map((atom) => [JSON.stringify(atom.position), atom]));

    const bonds = svgEl('g', { class: 'viewer-output-product-bonds' });
    for (const bond of product?.bonds || []) {
      const fromPosition = transform(bond.from || [0, 0], part);
      const toPosition = transform(bond.to || [0, 0], part);
      if (!atomAt.has(JSON.stringify(fromPosition)) || !atomAt.has(JSON.stringify(toPosition))) continue;
      const [x1, y1] = axialToPixel(fromPosition);
      const [x2, y2] = axialToPixel(toPosition);
      bonds.append(svgEl('line', {
        x1, y1, x2, y2,
        stroke: '#21180f',
        'stroke-width': bond.type === 'triplex' ? 12 : 9,
        'stroke-linecap': 'round',
        opacity: .92
      }));
      bonds.append(svgEl('line', {
        x1, y1, x2, y2,
        stroke: bond.type === 'triplex' ? '#efc366' : '#e5b96b',
        'stroke-width': bond.type === 'triplex' ? 7 : 4.5,
        'stroke-linecap': 'round',
        'stroke-dasharray': bond.type === 'triplex' ? 'none' : '5 4',
        opacity: .72
      }));
    }
    preview.append(bonds);

    const atomGroup = svgEl('g', { class: 'viewer-output-product-atoms' });
    for (const atom of atoms) {
      const [x, y] = axialToPixel(atom.position);
      atomGroup.append(svgEl('circle', {
        cx: x, cy: y, r: 18,
        fill: '#17120d',
        stroke: '#efc36e',
        'stroke-width': 3,
        'stroke-dasharray': '4 3',
        opacity: .95,
        class: 'viewer-output-target-ring'
      }));
      atomGroup.append(svgEl('circle', {
        cx: x, cy: y, r: 12.5,
        fill: COLORS[atom.element] || '#ddd',
        stroke: '#fff5d7',
        'stroke-width': 1.3,
        'stroke-opacity': .52,
        opacity: .68,
        class: 'viewer-output-target-core'
      }));
      atomGroup.append(svgEl('circle', {
        cx: x - 4, cy: y - 5, r: 3,
        fill: '#fff', opacity: .32
      }));
    }
    preview.append(atomGroup);
    group.classList.add('output-preview-ready');
    group.append(preview);
  }

  window.addEventListener('opus:analysisready', (event) => {
    const payload = event.detail?.payload;
    const puzzle = payload?.puzzle;
    const solution = payload?.solution;
    if (!puzzle || !solution) return;
    for (const part of solution.parts || []) {
      if (!String(part.type || '').startsWith('out-')) continue;
      const product = puzzle.products?.[Number(part.which || 0)];
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (group && product) drawOutputPreview(group, part, product);
    }
  });
})();
