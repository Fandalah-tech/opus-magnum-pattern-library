(() => {
  if (!window.OpusJS?.render) return;

  const originalRender = window.OpusJS.render;
  const NS = 'http://www.w3.org/2000/svg';
  const SQRT3 = Math.sqrt(3);
  let renderId = 0;

  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };

  const axial = (q, r, size, ox, oy) => ({
    x: ox + size * SQRT3 * (q + r / 2),
    y: oy + size * 1.5 * r
  });

  const hexPoints = size => Array.from({ length: 6 }, (_, index) => {
    const angle = Math.PI / 180 * (60 * index - 30);
    return `${size * Math.cos(angle)},${size * Math.sin(angle)}`;
  }).join(' ');

  function addDefs(svg, id) {
    const defs = svg.querySelector('defs') || svg.insertBefore(svgEl('defs'), svg.firstChild);

    const brass = svgEl('linearGradient', { id: `glyph-brass-${id}`, x1: '8%', y1: '5%', x2: '92%', y2: '95%' });
    [['0%','#ead09a'],['18%','#9f7948'],['45%','#3f2e20'],['68%','#b58c55'],['100%','#2a2019']]
      .forEach(([offset, color]) => brass.appendChild(svgEl('stop', { offset, 'stop-color': color })));
    defs.appendChild(brass);

    const plate = svgEl('radialGradient', { id: `glyph-plate-${id}`, cx: '42%', cy: '30%', r: '78%' });
    [['0%','#54534a'],['34%','#353731'],['70%','#181c1a'],['100%','#080b0a']]
      .forEach(([offset, color]) => plate.appendChild(svgEl('stop', { offset, 'stop-color': color })));
    defs.appendChild(plate);

    const glow = svgEl('radialGradient', { id: `glyph-glow-${id}`, cx: '50%', cy: '50%', r: '62%' });
    [['0%','#f5d4ec'],['30%','#b34f98'],['70%','#6a1d58'],['100%','#25091f']]
      .forEach(([offset, color]) => glow.appendChild(svgEl('stop', { offset, 'stop-color': color })));
    defs.appendChild(glow);

    const shadow = svgEl('filter', { id: `glyph-shadow-${id}`, x: '-50%', y: '-50%', width: '200%', height: '220%' });
    shadow.appendChild(svgEl('feDropShadow', { dx: 0, dy: 2.8, stdDeviation: 2.3, 'flood-color': '#000', 'flood-opacity': .78 }));
    defs.appendChild(shadow);
  }

  function drawPlate(layer, point, board, id) {
    const group = svgEl('g', {
      transform: `translate(${point.x} ${point.y})`,
      filter: `url(#glyph-shadow-${id})`,
      'data-glyph-base': 'masterGlyphV1'
    });

    group.appendChild(svgEl('polygon', {
      points: hexPoints(board.size - 2),
      fill: '#0c100f',
      stroke: '#8a6940',
      'stroke-width': 1.4
    }));
    group.appendChild(svgEl('polygon', {
      points: hexPoints(board.size - 5),
      fill: '#151a18',
      stroke: '#050706',
      'stroke-width': 1
    }));
    group.appendChild(svgEl('circle', {
      r: 30.5,
      fill: '#050706',
      stroke: `url(#glyph-brass-${id})`,
      'stroke-width': 5.1
    }));
    group.appendChild(svgEl('circle', {
      r: 25.7,
      fill: `url(#glyph-plate-${id})`,
      stroke: '#c09a62',
      'stroke-width': 1.05
    }));
    group.appendChild(svgEl('circle', {
      r: 22.2,
      fill: 'none',
      stroke: '#090c0b',
      'stroke-width': 2.2,
      opacity: .92
    }));
    group.appendChild(svgEl('ellipse', {
      cx: -7,
      cy: -10,
      rx: 12,
      ry: 4.4,
      fill: '#fff',
      opacity: .07,
      transform: 'rotate(-18)'
    }));
    return group;
  }

  function drawProjectionIcon(group, id) {
    group.appendChild(svgEl('circle', {
      r: 12,
      fill: `url(#glyph-glow-${id})`,
      stroke: '#e4bed8',
      'stroke-width': 1.3
    }));
    group.appendChild(svgEl('circle', {
      r: 6.2,
      fill: '#3b0c31',
      stroke: '#f0d8e8',
      'stroke-width': 1
    }));
    [0, 90, 180, 270].forEach(angle => {
      group.appendChild(svgEl('path', {
        d: 'M0,-29 L5.2,-19.5 L-5.2,-19.5 Z',
        fill: '#eee5d4',
        stroke: '#625b4f',
        'stroke-width': .45,
        transform: `rotate(${angle})`
      }));
    });
  }

  function drawBondingIcon(group) {
    const paths = [
      'M-15,-10 C-9,-10 -5,-6 0,0 C5,-6 9,-10 15,-10',
      'M-15,10 C-9,10 -5,6 0,0 C5,6 9,10 15,10'
    ];
    paths.forEach(path => {
      group.appendChild(svgEl('path', {
        d: path,
        fill: 'none',
        stroke: '#0b0d0c',
        'stroke-width': 6.2,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round'
      }));
      group.appendChild(svgEl('path', {
        d: path,
        fill: 'none',
        stroke: '#e8dfcc',
        'stroke-width': 3.1,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round'
      }));
    });
    group.appendChild(svgEl('circle', { r: 3.3, fill: '#d7b06d', stroke: '#4a3823', 'stroke-width': 1 }));
  }

  function drawGlyph(layer, item, scene, id) {
    const board = { size: 42, offsetX: 66, offsetY: 55, ...(scene.board || {}) };
    const point = axial(item.q, item.r, board.size, board.offsetX, board.offsetY);
    const group = drawPlate(layer, point, board, id);
    group.setAttribute('data-glyph', item.type || 'unknown');

    if (item.type === 'projection') drawProjectionIcon(group, id);
    else if (item.type === 'bonding') drawBondingIcon(group);

    layer.appendChild(group);
  }

  window.OpusJS.render = scene => {
    const glyphs = scene.glyphs || [];
    const cleanScene = { ...scene, glyphs: [] };
    const markup = originalRender(cleanScene);
    if (!glyphs.length) return markup;

    const doc = new DOMParser().parseFromString(markup, 'image/svg+xml');
    const svg = doc.documentElement;
    const id = `glyph-${++renderId}`;
    addDefs(svg, id);

    const layer = svgEl('g', { 'data-glyph-layer': 'masterGlyphV1' });
    glyphs.forEach(item => drawGlyph(layer, item, scene, id));
    const foreground = svg.querySelector('g[data-arm-group], g[data-arm="simple"], g[data-piston-arm], g[data-atom]');
    svg.insertBefore(layer, foreground || null);

    return new XMLSerializer().serializeToString(svg);
  };

  window.OpusJS.version = '2.0.0';
})();