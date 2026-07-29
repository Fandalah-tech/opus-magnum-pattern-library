(() => {
  if (!window.OpusJS?.render) return;

  const originalRender = window.OpusJS.render;
  const NS = 'http://www.w3.org/2000/svg';
  const SQRT3 = Math.sqrt(3);

  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };

  const axial = (q, r, size, ox, oy) => ({
    x: ox + size * SQRT3 * (q + r / 2),
    y: oy + size * 1.5 * r
  });

  function addTrackDefs(svg, id) {
    const defs = svg.querySelector('defs') || svg.insertBefore(svgEl('defs'), svg.firstChild);
    const metal = svgEl('linearGradient', { id: `track-metal-${id}`, x1: '0%', y1: '0%', x2: '0%', y2: '100%' });
    [['0%', '#f2f3f1'], ['24%', '#c8cccb'], ['52%', '#6c7375'], ['78%', '#bcc1c0'], ['100%', '#454b4e']]
      .forEach(([offset, color]) => metal.appendChild(svgEl('stop', { offset, 'stop-color': color })));
    defs.appendChild(metal);
  }

  function normalizedSegments(track) {
    if (Array.isArray(track.points) && track.points.length > 1) {
      return track.points.slice(0, -1).map((point, index) => [point, track.points[index + 1]]);
    }
    return [[{ q: track.q1, r: track.r1 }, { q: track.q2, r: track.r2 }]];
  }

  function renderTrackLayer(svg, scene, id) {
    const tracks = scene.tracks || [];
    if (!tracks.length) return;

    const board = { size: 42, offsetX: 66, offsetY: 55, ...(scene.board || {}) };
    const layer = svgEl('g', { 'data-track-layer': 'masterTrackV1' });
    const joints = new Map();

    tracks.flatMap(normalizedSegments).forEach(([start, end]) => {
      const a = axial(start.q, start.r, board.size, board.offsetX, board.offsetY);
      const b = axial(end.q, end.r, board.size, board.offsetX, board.offsetY);
      joints.set(`${a.x.toFixed(3)},${a.y.toFixed(3)}`, a);
      joints.set(`${b.x.toFixed(3)},${b.y.toFixed(3)}`, b);

      layer.appendChild(svgEl('line', { x1: a.x, y1: a.y + 2.2, x2: b.x, y2: b.y + 2.2, stroke: '#020403', 'stroke-width': 16, 'stroke-linecap': 'round', opacity: .78 }));
      layer.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#75562d', 'stroke-width': 12.5, 'stroke-linecap': 'round' }));
      layer.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#171d1c', 'stroke-width': 8.2, 'stroke-linecap': 'round' }));
      layer.appendChild(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: `url(#track-metal-${id})`, 'stroke-width': 3.15, 'stroke-linecap': 'round' }));
      layer.appendChild(svgEl('line', { x1: a.x, y1: a.y - 1.05, x2: b.x, y2: b.y - 1.05, stroke: '#f2eee2', 'stroke-width': .7, 'stroke-linecap': 'round', opacity: .72 }));
    });

    joints.forEach(point => {
      layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y + 1.4, r: 7.4, fill: '#020403', opacity: .72 }));
      layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 6.5, fill: '#75562d', stroke: '#241b12', 'stroke-width': .85 }));
      layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 4.35, fill: '#171d1c', stroke: '#b58d54', 'stroke-width': .7 }));
      layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 1.65, fill: `url(#track-metal-${id})`, stroke: '#f2eee2', 'stroke-width': .35 }));
    });

    const firstForeground = svg.querySelector('g[data-arm-group], g[data-arm="simple"], g[data-atom]');
    svg.insertBefore(layer, firstForeground || null);
  }

  window.OpusJS.render = scene => {
    const markup = originalRender(scene);
    const doc = new DOMParser().parseFromString(markup, 'image/svg+xml');
    const svg = doc.documentElement;
    const id = `v1-${Date.now().toString(36)}`;
    addTrackDefs(svg, id);
    renderTrackLayer(svg, scene, id);
    return new XMLSerializer().serializeToString(svg);
  };

  window.OpusJS.version = '1.6.0';
})();
