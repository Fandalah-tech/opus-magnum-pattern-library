(() => {
  if (window.OpusSvgDiffOverlay) return;
  const CORE = window.OpusRendererCore;
  if (!CORE) throw new Error('OpusRendererCore must load before opus-svg-diff-overlay.js');

  const SIZE = CORE.HEX_SIZE;
  const COLORS = Object.freeze({
    added: '#69b8a1',
    removed: '#de7e63',
    moved: '#f4d58d',
    changed: '#9a83bb'
  });

  class SvgDiffOverlay {
    constructor(layer) {
      if (!layer) throw new Error('SvgDiffOverlay requires an SVG layer');
      this.layer = layer;
    }

    clear() {
      this.layer.replaceChildren();
      return this;
    }

    drawCell(cell, mode) {
      const [x, y] = CORE.axialToPixel(cell);
      this.layer.append(CORE.svgEl('polygon', {
        points: CORE.hexPoints(x, y, SIZE * .83),
        fill: COLORS[mode],
        'fill-opacity': mode === 'removed' ? .12 : .18,
        stroke: COLORS[mode],
        'stroke-opacity': .95,
        'stroke-width': 2.5,
        'stroke-dasharray': mode === 'removed' ? '5 4' : null,
        class: `opus-diff-cell opus-diff-${mode}`,
        'data-diff-kind': mode
      }));
    }

    drawMoved(item) {
      const [x1, y1] = CORE.axialToPixel(item.from);
      const [x2, y2] = CORE.axialToPixel(item.to);
      this.layer.append(CORE.svgEl('line', {
        x1, y1, x2, y2,
        stroke: COLORS.moved,
        'stroke-width': 3.5,
        'stroke-linecap': 'round',
        'stroke-dasharray': '7 5',
        class: 'opus-diff-move-line',
        'data-diff-kind': 'moved',
        'data-before-part-id': item.before?.id || '',
        'data-after-part-id': item.after?.id || ''
      }));
      this.layer.append(CORE.svgEl('circle', {
        cx: x1, cy: y1, r: 8,
        fill: 'none', stroke: COLORS.removed, 'stroke-width': 2.5,
        class: 'opus-diff-move-origin', 'data-diff-kind': 'moved-origin'
      }));
      this.layer.append(CORE.svgEl('circle', {
        cx: x2, cy: y2, r: 10,
        fill: 'none', stroke: COLORS.added, 'stroke-width': 3,
        class: 'opus-diff-move-target', 'data-diff-kind': 'moved-target'
      }));
    }

    drawChanged(item) {
      const [x, y] = CORE.axialToPixel(item.after?.position || item.to || [0, 0]);
      this.layer.append(CORE.svgEl('circle', {
        cx: x, cy: y, r: SIZE * .62,
        fill: 'none', stroke: COLORS.changed,
        'stroke-width': 3.2,
        class: 'opus-diff-changed-ring',
        'data-diff-kind': 'changed',
        'data-part-id': item.after?.id || item.before?.id || ''
      }));
    }

    render(diff) {
      if (diff?.kind !== 'opus-scene-diff') throw new Error('SvgDiffOverlay.render requires an Opus scene diff');
      this.clear();
      for (const cell of diff.occupancy?.removed || []) this.drawCell(cell, 'removed');
      for (const cell of diff.occupancy?.added || []) this.drawCell(cell, 'added');
      for (const item of diff.parts?.moved || []) this.drawMoved(item);
      for (const item of diff.parts?.changed || []) this.drawChanged(item);
      this.layer.dataset.diffAddedParts = String(diff.summary?.addedParts || 0);
      this.layer.dataset.diffRemovedParts = String(diff.summary?.removedParts || 0);
      this.layer.dataset.diffMovedParts = String(diff.summary?.movedParts || 0);
      this.layer.dataset.diffChangedParts = String(diff.summary?.changedParts || 0);
      return this;
    }
  }

  window.OpusSvgDiffOverlay = Object.freeze({
    create(layer) { return new SvgDiffOverlay(layer); },
    SvgDiffOverlay,
    COLORS
  });
})();
