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

  function pointsFor(track) {
    if (Array.isArray(track.points) && track.points.length > 1) return track.points;
    return [{ q: track.q1, r: track.r1 }, { q: track.q2, r: track.r2 }];
  }

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
    const railOffset = 5.1;

    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y + 2.5, x2: b.x, y2: b.y + 2.5,
      stroke: '#020302', 'stroke-width': 20, 'stroke-linecap': 'round', opacity: .82
    }));
    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: '#17120d', 'stroke-width': 17, 'stroke-linecap': 'round'
    }));
    layer.appendChild(svgEl('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: '#050706', 'stroke-width': 11.2, 'stroke-linecap': 'round'
    }));

    [-railOffset, railOffset].forEach(offset => {
      layer.appendChild(svgEl('line', {
        x1: a.x + nx * offset, y1: a.y + ny * offset,
        x2: b.x + nx * offset, y2: b.y + ny * offset,
        stroke: '#3b2a18', 'stroke-width': 4.3, 'stroke-linecap': 'round'
      }));
      layer.appendChild(svgEl('line', {
        x1: a.x + nx * offset, y1: a.y + ny * offset - .45,
        x2: b.x + nx * offset, y2: b.y + ny * offset - .45,
        stroke: '#a47b42', 'stroke-width': 2.55, 'stroke-linecap': 'round'
      }));
      layer.appendChild(svgEl('line', {
        x1: a.x + nx * offset, y1: a.y + ny * offset - 1,
        x2: b.x + nx * offset, y2: b.y + ny * offset - 1,
        stroke: '#d7b06d', 'stroke-width': .65, 'stroke-linecap': 'round', opacity: .72
      }));
    });
  }

  function joint(layer, point) {
    layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y + 2, r: 10.4, fill: '#020302', opacity: .8 }));
    layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 9.1, fill: '#17120d', stroke: '#5f4529', 'stroke-width': 1.1 }));
    layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 6.25, fill: '#050706', stroke: '#a47b42', 'stroke-width': 1.45 }));
    layer.appendChild(svgEl('circle', { cx: point.x, cy: point.y, r: 2.15, fill: '#dfc88f', stroke: '#6f5a35', 'stroke-width': .65 }));
  }

  function markerText(layer, x, y, label) {
    const text = svgEl('text', {
      x, y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
      'font-family': 'Georgia, Times New Roman, serif', 'font-size': 18,
      'font-weight': 700, fill: '#e8d6a5', stroke: '#17120d', 'stroke-width': 1.1,
      'paint-order': 'stroke', 'data-track-marker': label
    });
    text.textContent = label;
    layer.appendChild(text);
  }

  function marker(layer, point, neighbor, label) {
    const dx = neighbor.x - point.x;
    const dy = neighbor.y - point.y;
    const length = Math.hypot(dx, dy) || 1;
    const nx = -dy / length;
    const ny = dx / length;
    markerText(layer, point.x + nx * 17, point.y + ny * 17, label);
  }

  function loopMarkerPair(layer, point, neighbor) {
    const dx = neighbor.x - point.x;
    const dy = neighbor.y - point.y;
    const length = Math.hypot(dx, dy) || 1;
    const nx = -dy / length;
    const ny = dx / length;
    markerText(layer, point.x + nx * 17, point.y + ny * 17, '+');
    markerText(layer, point.x - nx * 17, point.y - ny * 17, '−');
  }

  function renderTrack(layer, track, board) {
    const source = pointsFor(track);
    const loop = track.loop === true || (source.length > 2 && source[0].q === source[source.length - 1].q && source[0].r === source[source.length - 1].r);
    const points = source.map(point => axial(point.q, point.r, board.size, board.offsetX, board.offsetY));
    const uniquePoints = loop && points.length > 1 ? points.slice(0, -1) : points;
    const segmentCount = loop ? uniquePoints.length : uniquePoints.length - 1;

    for (let index = 0; index < segmentCount; index++) {
      const a = uniquePoints[index];
      const b = uniquePoints[(index + 1) % uniquePoints.length];
      segment(layer, a, b);
    }
    uniquePoints.forEach(point => joint(layer, point));

    if (loop) {
      const markerIndex = Math.max(0, Math.min(uniquePoints.length - 1, Number.isInteger(track.markerIndex) ? track.markerIndex : 0));
      const neighbor = uniquePoints[(markerIndex + 1) % uniquePoints.length] || uniquePoints[markerIndex];
      loopMarkerPair(layer, uniquePoints[markerIndex], neighbor);
      return;
    }

    const minusIndex = Math.max(0, Math.min(uniquePoints.length - 1, Number.isInteger(track.minusIndex) ? track.minusIndex : 0));
    const plusIndex = Math.max(0, Math.min(uniquePoints.length - 1, Number.isInteger(track.plusIndex) ? track.plusIndex : uniquePoints.length - 1));
    const minusNeighbor = uniquePoints[Math.min(minusIndex + 1, uniquePoints.length - 1)] || uniquePoints[minusIndex];
    const plusNeighbor = uniquePoints[Math.max(plusIndex - 1, 0)] || uniquePoints[plusIndex];
    marker(layer, uniquePoints[minusIndex], minusNeighbor, '−');
    marker(layer, uniquePoints[plusIndex], plusNeighbor, '+');
  }

  function renderTrackLayer(svg, scene) {
    const tracks = scene.tracks || [];
    if (!tracks.length) return;
    const board = { size: 42, offsetX: 66, offsetY: 55, ...(scene.board || {}) };
    const layer = svgEl('g', { 'data-track-layer': 'masterTrackV2' });
    tracks.forEach(track => renderTrack(layer, track, board));
    const foreground = svg.querySelector('g[data-arm-group], g[data-arm="simple"], g[data-atom]');
    svg.insertBefore(layer, foreground || null);
  }

  window.OpusJS.render = scene => {
    const markup = originalRender(scene);
    const doc = new DOMParser().parseFromString(markup, 'image/svg+xml');
    const svg = doc.documentElement;
    removeLegacyTracks(svg);
    renderTrackLayer(svg, scene);
    return new XMLSerializer().serializeToString(svg);
  };

  window.OpusJS.version = '1.8.1';
})();