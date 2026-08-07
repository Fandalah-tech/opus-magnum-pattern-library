(() => {
  if (window.OpusSvgDiagnosticsOverlay) return;
  const CORE = window.OpusRendererCore;
  if (!CORE) throw new Error('OpusRendererCore must load before opus-svg-diagnostics-overlay.js');

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
      const diagnostics = scene.annotations?.diagnostics?.items || [];
      const allowed = options.severities ? new Set(options.severities.map(String)) : null;
      const filtered = diagnostics.filter(item => !allowed || allowed.has(String(item.severity)));
      const parts = new Map((scene.static?.parts || []).map(part => [String(part.id), part]));
      const byPart = new Map();
      let globalCount = 0;

      for (const diagnostic of filtered) {
        const targets = (diagnostic.targets || []).filter(target => parts.has(String(target)));
        if (!targets.length) {
          globalCount += 1;
          continue;
        }
        for (const target of targets) {
          const key = String(target);
          if (!byPart.has(key)) byPart.set(key, []);
          byPart.get(key).push(diagnostic);
        }
      }

      for (const [partId, items] of byPart.entries()) {
        const part = parts.get(partId);
        if (!part) continue;
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

      this.layer.dataset.diagnosticCount = String(filtered.length);
      this.layer.dataset.targetedDiagnosticCount = String([...byPart.values()].reduce((sum, items) => sum + items.length, 0));
      this.layer.dataset.globalDiagnosticCount = String(globalCount);
      return {
        diagnostics: filtered.length,
        targetedParts: byPart.size,
        targetedDiagnostics: Number(this.layer.dataset.targetedDiagnosticCount),
        globalDiagnostics: globalCount
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
