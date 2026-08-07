(() => {
  if (window.OpusSvgOverlayHost) return;
  const CORE = window.OpusRendererCore;
  if (!CORE) throw new Error('OpusRendererCore must load before opus-svg-overlay-host.js');

  class SvgOverlayHost {
    constructor(world) {
      if (!world) throw new Error('SvgOverlayHost requires an SVG world group');
      this.world = world;
    }

    find(name) {
      return this.world.querySelector(`[data-opus-overlay="${CSS.escape(String(name))}"]`);
    }

    ensure(name, options = {}) {
      const id = String(name);
      let layer = this.find(id);
      if (!layer) {
        layer = CORE.svgEl('g', {
          class: options.className || `viewer-layer viewer-layer-${id}`,
          'data-opus-overlay': id,
          'data-viewer-layer': options.viewerLayer || id,
          'pointer-events': options.pointerEvents || 'none'
        });
        const before = options.before
          ? this.world.querySelector(`[data-viewer-layer="${CSS.escape(String(options.before))}"]`)
          : null;
        const after = !before && options.after
          ? this.world.querySelector(`[data-viewer-layer="${CSS.escape(String(options.after))}"]`)
          : null;
        if (before) this.world.insertBefore(layer, before);
        else if (after?.nextSibling) this.world.insertBefore(layer, after.nextSibling);
        else this.world.append(layer);
      }
      return layer;
    }

    clear(name) {
      const layer = this.find(name);
      layer?.replaceChildren();
      return layer || null;
    }

    remove(name) {
      this.find(name)?.remove();
    }

    names() {
      return [...this.world.querySelectorAll('[data-opus-overlay]')].map(node => node.dataset.opusOverlay);
    }
  }

  window.OpusSvgOverlayHost = Object.freeze({
    create(world) { return new SvgOverlayHost(world); },
    SvgOverlayHost
  });
})();
