(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  let viewer = null;
  let pointerStart = null;

  function neutralInspector() {
    return `
      <header class="viewer-inspector-head viewer-inspector-empty">
        <span class="viewer-kind-badge">board</span>
        <div><h4>Nothing selected</h4><p>Click a part, atom, or molecule to inspect it.</p></div>
      </header>
      <section class="viewer-inspector-section">
        <p class="hint">The replay remains fully visible while no object is selected.</p>
      </section>
    `;
  }

  function clearSelection() {
    if (!viewer) return;
    viewer.selectedId = null;
    viewer.world?.querySelectorAll('[data-part-id]').forEach((node) => {
      node.classList.remove('selected', 'related', 'dimmed', 'hovered');
    });
    viewer.layer?.('overlay')?.replaceChildren();
    if (viewer.details) viewer.details.innerHTML = neutralInspector();
    root.dispatchEvent(new CustomEvent('opus:viewercleared', { bubbles: true }));
  }

  function isInspectable(target) {
    return Boolean(target?.closest?.('[data-part-id], [data-atom-id], [data-molecule-id]'));
  }

  window.addEventListener('opus:sceneready', (event) => {
    viewer = event.detail?.viewer || viewer;
    window.__OPUS_VIEWER__ = viewer;
    window.__OPUS_LAST_SCENE__ = event.detail?.scene || null;
    window.__OPUS_CLEAR_SELECTION__ = clearSelection;
    window.__OPUS_CAPTURE_READY__ = true;

    clearSelection();

    const svg = viewer?.svg || root.querySelector('svg');
    if (!svg || svg.dataset.emptyDeselectBound === 'true') return;
    svg.dataset.emptyDeselectBound = 'true';

    svg.addEventListener('pointerdown', (pointerEvent) => {
      pointerStart = {
        x: pointerEvent.clientX,
        y: pointerEvent.clientY,
        inspectable: isInspectable(pointerEvent.target)
      };
    }, true);

    svg.addEventListener('pointerup', (pointerEvent) => {
      if (!pointerStart) return;
      const distance = Math.hypot(
        pointerEvent.clientX - pointerStart.x,
        pointerEvent.clientY - pointerStart.y
      );
      const shouldClear = !pointerStart.inspectable && !isInspectable(pointerEvent.target) && distance < 6;
      pointerStart = null;
      if (shouldClear) clearSelection();
    }, true);

    svg.addEventListener('pointercancel', () => { pointerStart = null; }, true);
  });

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') clearSelection();
  });
})();
