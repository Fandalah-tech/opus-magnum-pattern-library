(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';
  let press = null;
  let cycleBadge = null;

  function clearSelection() {
    const world = root.querySelector('[data-viewer-world]');
    world?.querySelectorAll('[data-part-id]').forEach((node) => {
      node.classList.remove('selected', 'related', 'dimmed');
    });
    world?.querySelector('[data-viewer-layer="overlay"]')?.replaceChildren();
    const details = root.querySelector('[data-viewer-details]');
    if (details) details.innerHTML = '<p class="hint">Sélectionnez une pièce, un atome ou une molécule pour l’inspecter.</p>';
  }

  function ensureCycleBadge() {
    if (cycleBadge?.isConnected) return cycleBadge;
    cycleBadge = document.createElement('div');
    cycleBadge.className = 'viewer-cycle-badge';
    cycleBadge.setAttribute('aria-live', 'polite');
    Object.assign(cycleBadge.style, {
      position: 'absolute', left: '12px', bottom: '12px', zIndex: '9',
      minWidth: '76px', padding: '7px 10px', border: '1px solid #3d352b',
      background: 'rgba(18,16,14,.88)', color: '#f1e8d8', fontSize: '11px',
      fontWeight: '800', letterSpacing: '.05em', textTransform: 'uppercase',
      pointerEvents: 'none', backdropFilter: 'blur(8px)'
    });
    cycleBadge.textContent = 'Cycle —';
    root.append(cycleBadge);
    return cycleBadge;
  }

  function addArmNumbers(solution) {
    const arms = (solution?.parts || []).filter((part) => /^(arm|piston|baron)/.test(part.type || ''));
    arms.forEach((part, armIndex) => {
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      if (!group || group.querySelector('[data-arm-number-label]')) return;
      const base = group.querySelector('[data-arm-base]');
      if (!base) return;
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
      label.textContent = String(part.armNumber ?? armIndex + 1);
      group.append(label);
    });
  }

  function activate(selector) {
    document.querySelector(selector)?.click();
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
    ensureCycleBadge();
    clearSelection();
    root.setAttribute('tabindex', '0');
  });

  root.addEventListener('opus:replayframe', (event) => {
    ensureCycleBadge().textContent = `Cycle ${event.detail?.frame?.cycle ?? '—'}`;
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

  document.addEventListener('keydown', (event) => {
    if (event.target.closest('input, select, textarea, button')) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); activate('[data-rotor-prev]'); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); activate('[data-rotor-next]'); }
    else if (event.key === 'Home') { event.preventDefault(); activate('[data-rotor-start]'); }
    else if (event.key.toLowerCase() === 's') { event.preventDefault(); activate('[data-rotor-solver-start]'); }
    else if (event.key === ' ') { event.preventDefault(); activate('[data-rotor-play]'); }
    else if (event.key === 'Escape') clearSelection();
  });
})();
