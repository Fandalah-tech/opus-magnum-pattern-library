(() => {
  const root = document.querySelector('#solution-viewer');
  const core = window.OpusRendererCore;
  const geometry = window.OpusGeometry;
  if (!root || !core || !geometry) return;

  const { axialToPixel, svgEl, ELEMENT_COLORS: COLORS } = core;
  let viewer = null;
  let scene = null;
  let outputs = new Map();
  let deliveryLayer = null;
  let animationFrame = null;

  const transform = (local, part) => {
    const rotated = geometry.rotateCell(local || [0, 0], Number(part.rotation || 0));
    return geometry.add(part.position || [0, 0], rotated);
  };

  function ensureLayer() {
    if (deliveryLayer?.isConnected) return deliveryLayer;
    const world = viewer?.world || root.querySelector('[data-viewer-world]');
    if (!world) return null;
    deliveryLayer = svgEl('g', {
      class: 'viewer-layer viewer-layer-delivery',
      'data-viewer-layer': 'delivery',
      'pointer-events': 'none'
    });
    const overlay = world.querySelector('[data-viewer-layer="overlay"]');
    world.insertBefore(deliveryLayer, overlay || null);
    return deliveryLayer;
  }

  function buildOutputs(nextScene) {
    scene = nextScene || null;
    outputs = new Map();
    const puzzle = scene?.source?.puzzle;
    for (const part of scene?.static?.parts || []) {
      if (!String(part.type || '').startsWith('out-')) continue;
      const product = puzzle?.products?.[Number(part.which || 0)];
      if (!product) continue;
      const atoms = (product.atoms || [])
        .filter((atom) => atom.element !== 'repeat')
        .map((atom) => ({
          element: atom.element,
          position: transform(atom.position || [0, 0], part)
        }));
      const centroid = atoms.length
        ? atoms.reduce((sum, atom) => [sum[0] + atom.position[0], sum[1] + atom.position[1]], [0, 0]).map((value) => value / atoms.length)
        : [...(part.position || [0, 0])];
      outputs.set(String(part.id), { part, atoms, centroid });
    }
  }

  function previousAtomsFor(deliveryEvent, frameScene) {
    const timeline = frameScene?.timeline || scene?.timeline;
    const index = Number(frameScene?.timeline?.frameIndex ?? timeline?.frameIndex ?? -1);
    const previous = index > 0 ? timeline?.frames?.[index - 1] : null;
    const wanted = new Set((deliveryEvent.atomIds || []).map(String));
    const atoms = [];
    const bonds = [];
    for (const molecule of previous?.molecules || []) {
      const moleculeAtoms = (molecule.atoms || []).filter((atom) => wanted.has(String(atom.id)));
      if (!moleculeAtoms.length) continue;
      atoms.push(...moleculeAtoms.map((atom) => ({ ...atom, position: [...atom.position] })));
      for (const bond of molecule.bonds || []) {
        const fromId = String(bond.fromAtomId || '');
        const toId = String(bond.toAtomId || '');
        if (wanted.has(fromId) && wanted.has(toId)) bonds.push({ ...bond });
      }
    }
    return { atoms, bonds };
  }

  function assignTargets(atoms, output) {
    const available = output.atoms.map((target, index) => ({ ...target, index, used: false }));
    const result = new Map();
    for (const atom of atoms) {
      const candidates = available.filter((target) => !target.used && target.element === atom.element);
      const pool = candidates.length ? candidates : available.filter((target) => !target.used);
      const target = pool.sort((a, b) => {
        const da = Math.hypot(a.position[0] - atom.position[0], a.position[1] - atom.position[1]);
        const db = Math.hypot(b.position[0] - atom.position[0], b.position[1] - atom.position[1]);
        return da - db;
      })[0];
      if (target) {
        target.used = true;
        result.set(String(atom.id), target.position);
      } else result.set(String(atom.id), output.centroid);
    }
    return result;
  }

  function mix(a, b, t) { return a + (b - a) * t; }

  function animateDelivery(deliveryEvent, frameScene, context = {}) {
    const output = outputs.get(String(deliveryEvent.consumerPartId));
    if (!output) return;
    const delivered = previousAtomsFor(deliveryEvent, frameScene);
    if (!delivered.atoms.length) return;
    const targets = assignTargets(delivered.atoms, output);
    const layer = ensureLayer();
    if (!layer) return;
    if (animationFrame) cancelAnimationFrame(animationFrame);
    layer.replaceChildren();

    const group = svgEl('g', {
      class: 'product-delivery-animation',
      'data-output-id': String(deliveryEvent.consumerPartId)
    });
    layer.append(group);
    const playing = Boolean(context.isPlaying);
    const baseDuration = Number(context.animationDuration ?? 560);
    const duration = playing ? Math.max(90, baseDuration * .96) : 560;
    const started = performance.now();
    const atomMap = new Map(delivered.atoms.map((atom) => [String(atom.id), atom]));

    const tick = (now) => {
      const raw = Math.min(1, (now - started) / duration);
      const moveT = 1 - Math.pow(1 - Math.min(1, raw / .72), 3);
      const fadeT = Math.max(0, (raw - .55) / .45);
      group.replaceChildren();

      for (const bond of delivered.bonds) {
        const first = atomMap.get(String(bond.fromAtomId));
        const second = atomMap.get(String(bond.toAtomId));
        if (!first || !second) continue;
        const firstTarget = targets.get(String(first.id)) || output.centroid;
        const secondTarget = targets.get(String(second.id)) || output.centroid;
        const startA = axialToPixel(first.position), startB = axialToPixel(second.position);
        const endA = axialToPixel(firstTarget), endB = axialToPixel(secondTarget);
        group.append(svgEl('line', {
          x1: mix(startA[0], endA[0], moveT), y1: mix(startA[1], endA[1], moveT),
          x2: mix(startB[0], endB[0], moveT), y2: mix(startB[1], endB[1], moveT),
          stroke: bond.type === 'triplex' ? '#f0c56f' : '#f4dfb2',
          'stroke-width': mix(bond.type === 'triplex' ? 7 : 4.5, 1, fadeT),
          'stroke-linecap': 'round', opacity: 1 - fadeT, class: 'product-delivery-bond'
        }));
      }

      for (const atom of delivered.atoms) {
        const target = targets.get(String(atom.id)) || output.centroid;
        const start = axialToPixel(atom.position), end = axialToPixel(target);
        const x = mix(start[0], end[0], moveT), y = mix(start[1], end[1], moveT);
        const radius = mix(13, 2.5, fadeT);
        group.append(svgEl('circle', {
          cx: x, cy: y, r: radius + 4, fill: '#1a140d', stroke: '#ffe39a',
          'stroke-width': mix(4, 1, fadeT), opacity: 1 - fadeT * .9, class: 'product-delivery-ring'
        }));
        group.append(svgEl('circle', {
          cx: x, cy: y, r: radius, fill: COLORS[atom.element] || '#ddd',
          opacity: 1 - fadeT, class: 'product-delivery-atom'
        }));
      }

      const [cx, cy] = axialToPixel(output.centroid);
      group.append(svgEl('circle', {
        cx, cy, r: 18 + raw * 22, fill: 'none', stroke: '#ffd783',
        'stroke-width': 3 - raw * 2, opacity: Math.max(0, 1 - raw), class: 'product-delivery-pulse'
      }));

      if (raw < 1) animationFrame = requestAnimationFrame(tick);
      else {
        animationFrame = null;
        layer.replaceChildren();
        root.dispatchEvent(new CustomEvent('opus:productdeliverycomplete', {
          bubbles: true,
          detail: { event: deliveryEvent, outputId: deliveryEvent.consumerPartId }
        }));
      }
    };
    animationFrame = requestAnimationFrame(tick);
  }

  window.addEventListener('opus:sceneready', (event) => {
    viewer = event.detail?.viewer || viewer;
    deliveryLayer = null;
    buildOutputs(event.detail?.scene);
    ensureLayer();
  });

  root.addEventListener('opus:replayframe', (event) => {
    const frameScene = event.detail?.scene || scene;
    const frame = frameScene?.timeline?.frame || event.detail?.frame;
    const delivery = (frame?.events || []).find((item) => item.kind === 'product-delivered');
    if (delivery) animateDelivery(delivery, frameScene, event.detail || {});
    else if (deliveryLayer) deliveryLayer.replaceChildren();
  });
})();
