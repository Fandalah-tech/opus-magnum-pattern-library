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
  const LABELS = {
    salt: 'S', air: 'A', earth: 'E', fire: 'F', water: 'W', quicksilver: 'Q',
    gold: 'Au', silver: 'Ag', copper: 'Cu', iron: 'Fe', tin: 'Sn', lead: 'Pb',
    vitae: 'V', mors: 'M', quintessence: 'Qe'
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
      if (child.hasAttribute('data-part-hit-targets')) continue;
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
        stroke: '#21170f',
        'stroke-width': bond.type === 'triplex' ? 12 : 9,
        'stroke-linecap': 'round',
        opacity: 1,
        class: 'viewer-output-target-bond-shadow'
      }));
      bonds.append(svgEl('line', {
        x1, y1, x2, y2,
        stroke: bond.type === 'triplex' ? '#f6c96c' : '#f0cf8d',
        'stroke-width': bond.type === 'triplex' ? 7 : 4.8,
        'stroke-linecap': 'round',
        opacity: .96,
        class: `viewer-output-target-bond viewer-output-target-bond-${bond.type || 'normal'}`
      }));
    }
    preview.append(bonds);

    const atomGroup = svgEl('g', { class: 'viewer-output-product-atoms' });
    for (const atom of atoms) {
      const [x, y] = axialToPixel(atom.position);
      atomGroup.append(svgEl('circle', {
        cx: x, cy: y, r: 17.5,
        fill: '#17120d',
        stroke: '#edae55',
        'stroke-width': 3.2,
        opacity: 1,
        class: 'viewer-output-target-ring'
      }));
      atomGroup.append(svgEl('circle', {
        cx: x, cy: y, r: 12.5,
        fill: COLORS[atom.element] || '#ddd',
        stroke: '#fff3d1',
        'stroke-width': 1.5,
        'stroke-opacity': .6,
        opacity: .94,
        class: 'viewer-output-target-core'
      }));
      atomGroup.append(svgEl('circle', {
        cx: x - 4, cy: y - 5, r: 3,
        fill: '#fff', opacity: .42
      }));
      const label = svgEl('text', {
        x,
        y: y + 4,
        'text-anchor': 'middle',
        fill: atom.element === 'salt' ? '#4e463b' : '#17120e',
        stroke: '#fff5df',
        'stroke-width': .55,
        'paint-order': 'stroke',
        'font-size': (LABELS[atom.element] || '?').length > 1 ? 7.5 : 9.5,
        'font-weight': 900,
        'font-family': 'ui-sans-serif,system-ui,sans-serif',
        class: 'viewer-output-target-label'
      });
      label.textContent = LABELS[atom.element] || '?';
      atomGroup.append(label);
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
