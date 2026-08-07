(() => {
  if (window.OpusSvgDiagnosticsOverlay) return;
  const CORE = window.OpusRendererCore;
  const SCENE = window.OpusScene;
  if (!CORE) throw new Error('OpusRendererCore must load before opus-svg-diagnostics-overlay.js');
  if (!SCENE) throw new Error('OpusScene must load before opus-svg-diagnostics-overlay.js');

  const SIZE = CORE.HEX_SIZE;
  const COLORS = Object.freeze({
    warning: '#de7e63',
    opportunity: '#f4d58d',
    info: '#69b8a1',
    unknown: '#9a83bb'
  });
  const PRIORITY = Object.freeze({ warning: 3, opportunity: 2, info: 1, unknown: 0 });

  class SvgDiagnosticsOverlay {
    constructor(layer) {
      if (!layer) throw new Error('SvgDiagnosticsOverlay requires an SVG layer');
      this.layer = layer;
    }

    clear() {
      this.layer.replaceChildren();
      delete this.layer.dataset.diagnosticCount;
      delete this.layer.dataset.targetedDiagnosticCount;
      delete this.layer.dataset.globalDiagnosticCount;
      return this;
    }

    render(scene, options = {}) {
      if (scene?.kind !== 'opus-scene') throw new Error('SvgDiagnosticsOverlay.render requires an Opus scene');
      this.clear();
      const query = { severities: options.severities, confidences: options.confidences };
      const filtered = SCENE.diagnostics(scene, query);
      const targeted = SCENE.targetedDiagnostics(scene, query);
      const global = SCENE.globalDiagnostics(scene, query);
      const byPart = new Map();

      for (const diagnostic of targeted) {
        for (const target of diagnostic.targets || []) {
          const part = SCENE.part(scene, target);
          if (!part) continue;
          const key = String(part.id);
          if (!byPart.has(key)) byPart.set(key, { part, items: [] });
          byPart.get(key).items.push(diagnostic);
        }
      }

      for (const [partId, entry] of byPart.entries()) {
        const { part, items } = entry;
        const severity = items.reduce((best, item) => {
          const current = String(item.severity || 'unknown');
          return (PRIORITY[current] ?? 0) > (PRIORITY[best] ?? 0) ? current : best;
        }, 'unknown');
        const color = COLORS[severity] || COLORS.unknown;
        const group = CORE.svgEl('g', {
          class: `opus-diagnostic-target opus-diagnostic-${severity}`,
          'data-opus-diagnostic-target': partId,
          'data-diagnostic-count': String(items.length),
          'data-diagnostic-severity': severity,
          'pointer-events': 'none'
        });
        for (const cell of part.occupiedCells || [part.position || [0, 0]]) {
          const [x, y] = CORE.axialToPixel(cell);
          group.append(CORE.svgEl('polygon', {
            points: CORE.hexPoints(x, y, SIZE * .78),
            fill: color,
            'fill-opacity': .08,
            stroke: color,
            'stroke-opacity': .92,
            'stroke-width': 2.8,
            'stroke-dasharray': severity === 'info' ? '5 4' : null,
            class: 'opus-diagnostic-footprint'
          }));
        }
        const [cx, cy] = CORE.axialToPixel(part.position || [0, 0]);
        group.append(CORE.svgEl('circle', {
          cx: cx + SIZE * .55,
          cy: cy - SIZE * .48,
          r: 10,
          fill: '#17120e',
          stroke: color,
          'stroke-width': 2.4,
          class: 'opus-diagnostic-badge'
        }));
        const label = CORE.svgEl('text', {
          x: cx + SIZE * .55,
          y: cy - SIZE * .48 + 3.7,
          'text-anchor': 'middle',
          fill: color,
          'font-size': 9,
          'font-weight': 900,
          'font-family': 'ui-sans-serif,system-ui,sans-serif',
          class: 'opus-diagnostic-count-label'
        });
        label.textContent = String(items.length);
        group.append(label);
        this.layer.append(group);
      }

      const targetedCount = [...byPart.values()].reduce((sum, entry) => sum + entry.items.length, 0);
      this.layer.dataset.diagnosticCount = String(filtered.length);
      this.layer.dataset.targetedDiagnosticCount = String(targetedCount);
      this.layer.dataset.globalDiagnosticCount = String(global.length);
      return {
        diagnostics: filtered.length,
        targetedParts: byPart.size,
        targetedDiagnostics: targetedCount,
        globalDiagnostics: global.length
      };
    }
  }

  window.OpusSvgDiagnosticsOverlay = Object.freeze({
    create(layer) { return new SvgDiagnosticsOverlay(layer); },
    SvgDiagnosticsOverlay,
    COLORS,
    PRIORITY
  });
})();
