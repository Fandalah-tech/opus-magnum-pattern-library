(() => {
  if (window.OpusSvgRenderer) return;
  const CORE = window.OpusRendererCore;
  const GEO = window.OpusGeometry;
  const SYMBOLS = window.OpusPieceSymbols;
  if (!CORE || !GEO) throw new Error('OpusRendererCore and OpusGeometry must load before opus-svg-renderer.js');

  const SIZE = CORE.HEX_SIZE;
  const COLORS = Object.freeze({
    arm: '#d4a457', armDark: '#3a2b1d', input: '#69b8a1', output: '#de7e63',
    track: '#8c7a61', trackCore: '#c6a976', glyph: '#9a83bb', selected: '#f4d58d',
    related: '#72c3b0', grid: '#3a342d', gridFill: '#161411', text: '#f1e8d7', muted: '#b8aa95'
  });
  const DEFAULT_LAYERS = ['grid', 'track', 'glyph', 'part', 'bond', 'atom', 'arm', 'overlay'];

  class SvgRenderer {
    constructor(world, options = {}) {
      if (!world) throw new Error('SvgRenderer requires an SVG world group');
      this.world = world;
      this.layers = new Map();
      this.layerOrder = options.layerOrder || DEFAULT_LAYERS;
      this.onPartActivate = options.onPartActivate || null;
      this.buildLayers();
    }

    buildLayers() {
      this.world.replaceChildren();
      this.layers.clear();
      for (const name of this.layerOrder) {
        const layer = CORE.svgEl('g', {
          class: `viewer-layer viewer-layer-${name}`,
          'data-viewer-layer': name
        });
        this.layers.set(name, layer);
        this.world.append(layer);
      }
    }

    layer(name) {
      if (!this.layers.has(name) || !this.layers.get(name)?.isConnected) this.buildLayers();
      return this.layers.get(name);
    }

    render(scene) {
      if (!scene?.static) throw new Error('SvgRenderer.render requires an Opus scene');
      this.buildLayers();
      this.drawGrid(scene.static.occupiedCells || []);
      for (const part of scene.static.parts || []) this.drawPart(part);
      return this;
    }

    drawGrid(positions) {
      if (!positions.length) return;
      const qs = positions.map(([q]) => q), rs = positions.map(([, r]) => r);
      const minQ = Math.min(...qs) - 5, maxQ = Math.max(...qs) + 5;
      const minR = Math.min(...rs) - 5, maxR = Math.max(...rs) + 5;
      const activeSet = new Set(positions.map(([q, r]) => `${q},${r}`));
      const grid = this.layer('grid');
      for (let q = minQ; q <= maxQ; q += 1) {
        for (let r = minR; r <= maxR; r += 1) {
          const [x, y] = CORE.axialToPixel([q, r]);
          const active = activeSet.has(`${q},${r}`);
          grid.append(CORE.svgEl('polygon', {
            points: CORE.hexPoints(x, y, SIZE * .92),
            fill: active ? COLORS.gridFill : 'transparent',
            'fill-opacity': active ? .72 : 0,
            stroke: COLORS.grid,
            'stroke-width': active ? 1.35 : .9,
            'stroke-opacity': active ? .9 : .58,
            class: active ? 'viewer-grid-cell active' : 'viewer-grid-cell'
          }));
        }
      }
    }

    drawPart(part) {
      const kind = part.kind || CORE.partKind(part.type);
      const targetLayer = kind === 'track' ? 'track' : kind === 'arm' ? 'arm' : kind === 'glyph' ? 'glyph' : 'part';
      const group = CORE.svgEl('g', {
        'data-part-id': part.id,
        'data-part-kind': kind,
        class: `viewer-part viewer-${kind}`,
        tabindex: 0,
        role: 'button',
        'aria-label': `${part.type} ${part.id}`
      });
      const activate = event => {
        event?.stopPropagation?.();
        this.onPartActivate?.(part.id, part, event);
      };
      group.addEventListener('click', activate);
      group.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          activate(event);
        }
      });
      group.addEventListener('pointerenter', () => group.classList.add('hovered'));
      group.addEventListener('pointerleave', () => group.classList.remove('hovered'));

      if (kind === 'track') this.drawTrack(group, part);
      else if (kind === 'arm') this.drawArm(group, part);
      else this.drawStation(group, part, kind);

      const title = CORE.svgEl('title');
      title.textContent = `${part.type} · ${part.id}`;
      group.append(title);
      this.layer(targetLayer).append(group);
    }

    drawTrack(group, part) {
      const cells = part.occupiedCells || GEO.occupiedCells(part);
      const points = cells.map(CORE.axialToPixel).map(([x, y]) => `${x},${y}`).join(' ');
      group.append(CORE.svgEl('polyline', { points, fill:'none', stroke:'#211d18', 'stroke-width':17, 'stroke-linecap':'round', 'stroke-linejoin':'round', class:'viewer-track-shadow' }));
      group.append(CORE.svgEl('polyline', { points, fill:'none', stroke:COLORS.track, 'stroke-width':10, 'stroke-linecap':'round', 'stroke-linejoin':'round', class:'viewer-track-rail' }));
      group.append(CORE.svgEl('polyline', { points, fill:'none', stroke:COLORS.trackCore, 'stroke-width':2.4, 'stroke-linecap':'round', 'stroke-linejoin':'round', 'stroke-dasharray':'3 8', class:'viewer-track-core' }));
      for (const cell of cells) {
        const [x, y] = CORE.axialToPixel(cell);
        group.append(CORE.svgEl('circle', { cx:x, cy:y, r:5.5, fill:'#241f19', stroke:COLORS.trackCore, 'stroke-width':2 }));
      }
    }

    drawArm(group, part) {
      const origin = part.position || [0,0];
      const [x, y] = CORE.axialToPixel(origin);
      const tips = part.armTips?.length ? part.armTips : CORE.armTips(part);
      group.dataset.branchCount = String(tips.length);
      for (const tip of tips) {
        const branchIndex = tip.branchIndex;
        const [ex, ey] = CORE.axialToPixel(tip.position);
        group.append(CORE.svgEl('line', { x1:x, y1:y, x2:ex, y2:ey, stroke:'#1f1a14', 'stroke-width':13, 'stroke-linecap':'round', 'data-arm-shadow':branchIndex }));
        group.append(CORE.svgEl('line', { x1:x, y1:y, x2:ex, y2:ey, stroke:COLORS.arm, 'stroke-width':7, 'stroke-linecap':'round', 'data-arm-shaft':branchIndex }));
        group.append(CORE.svgEl('circle', { cx:ex, cy:ey, r:11.5, fill:COLORS.armDark, stroke:COLORS.arm, 'stroke-width':4, 'data-arm-tip':branchIndex }));
        group.append(CORE.svgEl('circle', { cx:ex, cy:ey, r:4.2, fill:COLORS.arm, 'data-arm-grip':branchIndex }));
      }
      group.append(CORE.svgEl('circle', { cx:x, cy:y, r:17, fill:'#1b1814', stroke:'#5a452d', 'stroke-width':6, class:'viewer-arm-base-shadow' }));
      group.append(CORE.svgEl('circle', { cx:x, cy:y, r:14, fill:COLORS.armDark, stroke:COLORS.arm, 'stroke-width':3.5, 'data-arm-base':'true' }));
      group.append(CORE.svgEl('circle', { cx:x, cy:y, r:4.5, fill:COLORS.arm }));
    }

    drawStation(group, part, kind) {
      const cells = part.occupiedCells || GEO.occupiedCells(part);
      const color = COLORS[kind] || COLORS.glyph;
      const centers = cells.map(CORE.axialToPixel);
      const footprint = CORE.svgEl('g', { class:'viewer-piece-footprint' });
      for (const [x, y] of centers) {
        footprint.append(CORE.svgEl('polygon', { points:CORE.hexPoints(x,y,SIZE*.72), fill:color, 'fill-opacity':.09, stroke:color, 'stroke-opacity':.78, 'stroke-width':2.2 }));
        footprint.append(CORE.svgEl('polygon', { points:CORE.hexPoints(x,y,SIZE*.58), fill:'#12100e', 'fill-opacity':.74, stroke:'#251f19', 'stroke-width':1 }));
      }
      group.append(footprint);
      if (SYMBOLS?.draw) SYMBOLS.draw(group, part, centers, color, GEO.label(part.type));
      else {
        const [cx, cy] = CORE.axialToPixel(part.position || [0,0]);
        const label = CORE.svgEl('text', { x:cx, y:cy+5, 'text-anchor':'middle', fill:COLORS.text, 'font-size':12, 'font-weight':700 });
        label.textContent = GEO.label(part.type);
        group.append(label);
      }
    }
  }

  window.OpusSvgRenderer = Object.freeze({
    create(world, options) { return new SvgRenderer(world, options); },
    SvgRenderer,
    COLORS,
    DEFAULT_LAYERS
  });
})();
