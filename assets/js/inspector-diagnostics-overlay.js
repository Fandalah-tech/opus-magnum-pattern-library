(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const hostFactory = window.OpusSvgOverlayHost;
  const diagnosticsOverlay = window.OpusSvgDiagnosticsOverlay;
  if (!hostFactory || !diagnosticsOverlay) {
    throw new Error('Inspector diagnostics overlay requires OpusSvgOverlayHost and OpusSvgDiagnosticsOverlay');
  }

  let host = null;
  let layer = null;
  let overlay = null;
  let toggle = null;
  let visible = true;
  let lastStats = null;

  function ensureToggle() {
    if (toggle?.isConnected) return toggle;
    const tools = root.querySelector('.viewer-tools');
    if (!tools) return null;
    toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.dataset.diagnosticsOverlayToggle = 'true';
    toggle.textContent = 'Diagnostics';
    toggle.setAttribute('aria-pressed', String(visible));
    const zoom = tools.querySelector('[data-viewer-zoom]');
    tools.insertBefore(toggle, zoom || null);
    toggle.addEventListener('click', () => {
      if (!layer || toggle.disabled) return;
      visible = !visible;
      layer.hidden = !visible;
      toggle.setAttribute('aria-pressed', String(visible));
    });
    return toggle;
  }

  function render(scene, viewer) {
    const world = viewer?.world || root.querySelector('[data-viewer-world]');
    if (!world) return null;
    host = hostFactory.create(world);
    layer = host.ensure('diagnostics', {
      before: 'overlay',
      className: 'viewer-layer viewer-layer-diagnostics'
    });
    overlay = diagnosticsOverlay.create(layer);
    lastStats = overlay.render(scene);
    layer.hidden = !visible;

    const button = ensureToggle();
    if (button) {
      button.disabled = lastStats.targetedParts === 0;
      button.textContent = lastStats.targetedParts > 0
        ? `Diagnostics · ${lastStats.targetedParts}`
        : 'Diagnostics · 0';
      button.setAttribute('aria-pressed', String(visible && !button.disabled));
      button.title = lastStats.globalDiagnostics > 0
        ? `${lastStats.globalDiagnostics} global diagnostic(s) remain in the Inspector list.`
        : 'Toggle targeted optimization diagnostics on the machine.';
    }

    window.__OPUS_DIAGNOSTICS_OVERLAY__ = { host, layer, overlay, stats: lastStats };
    root.dispatchEvent(new CustomEvent('opus:diagnosticsoverlayready', {
      bubbles: true,
      detail: { scene, viewer, host, layer, stats: lastStats }
    }));
    return lastStats;
  }

  window.addEventListener('opus:sceneready', event => {
    render(event.detail?.scene, event.detail?.viewer);
  });

  window.OpusInspectorDiagnosticsOverlay = Object.freeze({
    render,
    stats: () => lastStats,
    visible: () => visible
  });
})();
