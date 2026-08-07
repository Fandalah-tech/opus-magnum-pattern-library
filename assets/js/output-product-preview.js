(() => {
  const root = document.querySelector('#solution-viewer');
  const core = window.OpusRendererCore;
  const geometry = window.OpusGeometry;
  if (!root || !core || !geometry) return;

  const LABELS = {
    salt: 'S', air: 'A', earth: 'E', fire: 'F', water: 'W', quicksilver: 'Q',
    gold: 'Au', silver: 'Ag', copper: 'Cu', iron: 'Fe', tin: 'Sn', lead: 'Pb',
    vitae: 'V', mors: 'M', quintessence: 'Qe'
  };
  const THEMES = {
    input: { ring: '#69b8a1', bond: '#92d8c5', triplex: '#b9efe0' },
    output: { ring: '#edae55', bond: '#f0cf8d', triplex: '#f6c96c' }
  };

  const transform = (local, part) => {
    const rotated = geometry.rotateCell(local || [0, 0], Number(part.rotation || 0));
    return geometry.add(part.position || [0, 0], rotated);
  };

  function removeGenericSymbol(group) {
    for (const child of [...group.children]) {
      if (child.tagName.toLowerCase() === 'title') continue;
      if (child.hasAttribute('data-part-hit-targets')) continue;
      child.remove();
    }
  }

  function previewAtoms(molecule, part) {
    return (molecule?.atoms || [])
      .filter(atom => atom.element !== 'repeat')
      .map((atom, index) => ({
        id: `preview-atom-${index}`,
        element: atom.element,
        position: transform(atom.position || [0, 0], part)
      }));
  }

  function drawMoleculePreview(group, part, molecule, mode) {
    if (!group || !molecule) return;
    const theme = THEMES[mode] || THEMES.output;
    removeGenericSymbol(group);
    const preview = core.svgEl('g', {
      class: `viewer-station-molecule viewer-${mode}-molecule`,
      [`data-${mode}-preview`]: 'true',
      'pointer-events': 'none'
    });
    const atoms = previewAtoms(molecule, part);
    const atomAt = new Set(atoms.map(atom => JSON.stringify(atom.position)));

    const bonds = core.svgEl('g', { class: `viewer-${mode}-molecule-bonds` });
    for (const bond of molecule?.bonds || []) {
      const fromPosition = transform(bond.from || [0, 0], part);
      const toPosition = transform(bond.to || [0, 0], part);
      if (!atomAt.has(JSON.stringify(fromPosition)) || !atomAt.has(JSON.stringify(toPosition))) continue;
      const [x1, y1] = core.axialToPixel(fromPosition);
      const [x2, y2] = core.axialToPixel(toPosition);
      bonds.append(core.svgEl('line', {
        x1, y1, x2, y2, stroke: '#21170f',
        'stroke-width': bond.type === 'triplex' ? 12 : 9,
        'stroke-linecap': 'round', opacity: 1,
        class: `viewer-${mode}-bond-shadow`
      }));
      bonds.append(core.svgEl('line', {
        x1, y1, x2, y2,
        stroke: bond.type === 'triplex' ? theme.triplex : theme.bond,
        'stroke-width': bond.type === 'triplex' ? 7 : 4.8,
        'stroke-linecap': 'round', opacity: .96,
        class: `viewer-${mode}-bond viewer-${mode}-bond-${bond.type || 'normal'}`
      }));
    }
    preview.append(bonds);

    const atomGroup = core.svgEl('g', { class: `viewer-${mode}-molecule-atoms` });
    for (const atom of atoms) {
      const [x, y] = core.axialToPixel(atom.position);
      atomGroup.append(core.svgEl('circle', {
        cx: x, cy: y, r: 17.5, fill: '#17120d', stroke: theme.ring,
        'stroke-width': 3.2, opacity: 1, class: `viewer-${mode}-atom-ring`
      }));
      atomGroup.append(core.svgEl('circle', {
        cx: x, cy: y, r: 12.5,
        fill: core.ELEMENT_COLORS[atom.element] || '#ddd',
        stroke: '#fff3d1', 'stroke-width': 1.5, 'stroke-opacity': .6,
        opacity: .94, class: `viewer-${mode}-atom-core`
      }));
      atomGroup.append(core.svgEl('circle', { cx: x - 4, cy: y - 5, r: 3, fill: '#fff', opacity: .42 }));
      const label = core.svgEl('text', {
        x, y: y + 4, 'text-anchor': 'middle',
        fill: atom.element === 'salt' ? '#4e463b' : '#17120e',
        stroke: '#fff5df', 'stroke-width': .55, 'paint-order': 'stroke',
        'font-size': (LABELS[atom.element] || '?').length > 1 ? 7.5 : 9.5,
        'font-weight': 900, 'font-family': 'ui-sans-serif,system-ui,sans-serif',
        class: `viewer-${mode}-atom-label`
      });
      label.textContent = LABELS[atom.element] || '?';
      atomGroup.append(label);
    }
    preview.append(atomGroup);
    group.classList.add(`${mode}-preview-ready`);
    group.append(preview);
  }

  window.addEventListener('opus:analysisready', (event) => {
    const payload = event.detail?.payload;
    const puzzle = payload?.puzzle;
    const solution = payload?.solution;
    if (!puzzle || !solution) return;
    for (const part of solution.parts || []) {
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (!group) continue;
      if (part.type === 'input') {
        const reagent = puzzle.reagents?.[Number(part.which || 0)];
        if (reagent) drawMoleculePreview(group, part, reagent, 'input');
      } else if (String(part.type || '').startsWith('out-')) {
        const product = puzzle.products?.[Number(part.which || 0)];
        if (product) drawMoleculePreview(group, part, product, 'output');
      }
    }
  });

  window.OpusStationMoleculePreview = Object.freeze({ drawMoleculePreview });
})();
