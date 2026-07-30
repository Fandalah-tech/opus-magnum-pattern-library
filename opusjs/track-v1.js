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

  const pointsFor = track => Array.isArray(track.points) && track.points.length > 1
    ? track.points
    : [{ q: track.q1, r: track.r1 }, { q: track.q2, r: track.r2 }];

  function removeLegacyTracks(svg) {
    svg.querySelectorAll('line').forEach(line => {
      const stroke = line.getAttribute('stroke');
      if (stroke === '#6a5124' || (stroke === '#e6dcc5' && line.hasAttribute('stroke-dasharray'))) line.remove();
    });
    svg.querySelectorAll('[data-track-layer]').forEach(layer => layer.remove());
  }

  function segment(layer, a, b) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = Math.hypot(dx, dy) || 1;
    const nx = -dy / length;
    const ny = dx / length;
    const railOffset = 6.25;

    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y + 3, x2: b.x, y2: b.y + 3,
      stroke: '#020302', 'stroke-width': 24, 'stroke-linecap': 'round', opacity: .84
    }));
    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: '#17120d', 'stroke-width': 20.5, 'stroke-linecap': 'round'
    }));
    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: '#050706', 'stroke-width': 13.5, 'stroke-linecap': 'round'
    }));

    [-railOffset, railOffset].forEach(offset => {
      const x1 = a.x + nx * offset;
      const y1 = a.y + ny * offset;
      const x2 = b.x + nx * offset;
      const y2 = b.y + ny * offset;
      layer.appendChild(svgEl('line', {
        x1, y1, x2, y2,
        stroke: '#3b2a18', 'stroke-width': 5.25, 'stroke-linecap': 'round'
      }));
      layer.appendChild(svgEl('line', {
        x1, y1: y1 - .55, x2, y2: y2 - .55,
        stroke: '#aa7d40', 'stroke-width': 3.25, 'stroke-linecap': 'round'
      }));
      layer.appendChild(svgEl('line', {
        x1, y1: y1 - 1.2, x2, y2: y2 - 1.2,
        stroke: '#e0b873', 'stroke-width': .8, 'stroke-linecap': 'round', opacity: .76
      }));
    });
  }

  function joint(layer, point, marker = null) {
    layer.appendChild(svgEl('circle', {
      cx: point.x, cy: point.y + 2.5, r: 12.4,
      fill: '#020302', opacity: .82
    }));
    layer.appendChild(svgEl('circle', {
      cx: point.x, cy: point.y, r: 11,
      fill: '#17120d', stroke: '#5f4529', 'stroke-width': 1.35
    }));
    layer.appendChild(svgEl('circle', {
      cx: point.x, cy: point.y, r: 7.8,
      fill: '#050706', stroke: '#a47b42', 'stroke-width': 1.75
    }));

    if (!marker) {
      layer.appendChild(svgEl('circle', {
        cx: point.x, cy: point.y, r: 2.5,
        fill: '#dfc88f', stroke: '#6f5a35', 'stroke-width': .7
      }));
      return;
    }

    const labels = marker === '±' ? [
      {label:'−', x:-3.6},
      {label:'+', x:3.6}
    ] : [{label:marker, x:0}];

    labels.forEach(({label, x}) => {
      const text = svgEl('text', {
        x: point.x + x,
        y: point.y + .55,
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
        'font-family': 'Georgia, Times New Roman, serif',
        'font-size': labels.length === 2 ? 8.6 : 12,
        'font-weight': 700,
        fill: '#ecd8a5',
        stroke: '#17120d',
        'stroke-width': .8,
        'paint-order': 'stroke',
        'data-track-marker': label
      });
      text.textContent = label;
      layer.appendChild(text);
    });
  }

  function renderTrack(layer, track, board) {
    const source = pointsFor(track);
    const loop = track.loop === true || (
      source.length > 2 &&
      source[0].q === source[source.length - 1].q &&
      source[0].r === source[source.length - 1].r
    );
    const points = source.map(point => axial(point.q, point.r, board.size, board.offsetX, board.offsetY));
    const uniquePoints = loop && points.length > 1 ? points.slice(0, -1) : points;
    const segmentCount = loop ? uniquePoints.length : uniquePoints.length - 1;

    for (let index = 0; index < segmentCount; index++) {
      segment(layer, uniquePoints[index], uniquePoints[(index + 1) % uniquePoints.length]);
    }

    if (loop) {
      const controlIndex = Math.max(
        0,
        Math.min(uniquePoints.length - 1, Number.isInteger(track.controlIndex) ? track.controlIndex : 0)
      );
      uniquePoints.forEach((point, index) => joint(layer, point, index === controlIndex ? '±' : null));
      return;
    }

    const last = uniquePoints.length - 1;
    uniquePoints.forEach((point, index) => {
      const marker = index === 0 ? '−' : (index === last ? '+' : null);
      joint(layer, point, marker);
    });
  }

  function renderTrackLayer(svg, scene) {
    const tracks = scene.tracks || [];
    if (!tracks.length) return;
    const board = { size: 42, offsetX: 66, offsetY: 55, ...(scene.board || {}) };
    const layer = svgEl('g', { 'data-track-layer': 'masterTrackV3' });
    tracks.forEach(track => renderTrack(layer, track, board));
    const foreground = svg.querySelector('g[data-arm-group], g[data-arm="simple"], g[data-piston-arm], g[data-atom]');
    svg.insertBefore(layer, foreground || null);
  }

  window.OpusJS.render = scene => {
    const doc = new DOMParser().parseFromString(originalRender(scene), 'image/svg+xml');
    const svg = doc.documentElement;
    removeLegacyTracks(svg);
    renderTrackLayer(svg, scene);
    return new XMLSerializer().serializeToString(svg);
  };

  window.OpusJS.version = '1.9.1';
})();