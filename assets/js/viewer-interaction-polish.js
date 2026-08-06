(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  let press = null;

  function clearSelection() {
    const world = root.querySelector('[data-viewer-world]');
    world?.querySelectorAll('[data-part-id]').forEach((node) => {
      node.classList.remove('selected', 'related', 'dimmed');
    });
    world?.querySelector('[data-viewer-layer="overlay"]')?.replaceChildren();
    const details = root.querySelector('[data-viewer-details]');
    if (details) details.innerHTML = '<p class="hint">Sélectionnez une pièce, un atome ou une molécule pour l’inspecter.</p>';
  }

  function addArmNumbers(solution) {
    const parts = solution?.parts || [];
    for (const part of parts) {
      if (!/^(arm|piston|baron)/.test(part.type || '')) continue;
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (!group || group.querySelector('[data-arm-number-label]')) continue;
      const base = group.querySelector('[data-arm-base]');
      if (!base) continue;
      const x = Number(base.getAttribute('cx')) || 0;
      const y = Number(base.getAttribute('cy')) || 0;
      const label = document.createElementNS(SVG_NS, 'text');
      label.setAttribute('x', x);
      label.setAttribute('y', y + 4.2);
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('font-size', '10');
      label.setAttribute('font-weight', '800');
      label.setAttribute('fill', '#f6e5bd');
      label.setAttribute('stroke', '#21180f');
      label.setAttribute('stroke-width', '2.5');
      label.setAttribute('paint-order', 'stroke');
      label.setAttribute('pointer-events', 'none');
      label.setAttribute('data-arm-number-label', 'true');
      label.textContent = String(part.armNumber ?? '?');
      group.append(label);
    }
  }

  root.addEventListener('pointerdown', (event) => {
    if (event.target.closest('[data-part-id], [data-atom-id], [data-molecule-id]')) return;
    press = { x: event.clientX, y: event.clientY };
  });

  root.addEventListener('pointerup', (event) => {
    if (!press) return;
    const distance = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (distance <= 4 && !event.target.closest('[data-part-id], [data-atom-id], [data-molecule-id]')) clearSelection();
  });

  root.addEventListener('pointercancel', () => { press = null; });
  root.addEventListener('opus:viewerready', (event) => {
    addArmNumbers(event.detail?.solution);
    clearSelection();
  });

  root.addEventListener('opus:replayframe', () => {
    requestAnimationFrame(() => {
      root.querySelectorAll('[data-arm-number-label]').forEach((label) => {
        const group = label.closest('[data-part-id]');
        const base = group?.querySelector('[data-arm-base]');
        if (!base) return;
        label.setAttribute('x', base.getAttribute('cx') || '0');
        label.setAttribute('y', String((Number(base.getAttribute('cy')) || 0) + 4.2));
      });
    });
  });
})();
