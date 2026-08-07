(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const core = window.OpusRendererCore;
  if (!core) throw new Error('OpusRendererCore must load before replay-arm-animation.js');
  const activeAnimations = new Map();

  function branchGeometry(state) {
    const origin = state.origin || [0, 0];
    const [x1, y1] = core.axialToPixel(origin);
    const tips = state.tips || [];
    return tips.map((tip, branchIndex) => {
      const [x2, y2] = core.axialToPixel(tip.position || origin);
      return { branchIndex: tip.branchIndex ?? branchIndex, x1, y1, x2, y2 };
    });
  }

  function numberAttr(node, name, fallback) {
    const value = Number(node?.getAttribute(name));
    return Number.isFinite(value) ? value : fallback;
  }

  function setLine(node, x1, y1, x2, y2) {
    if (!node) return;
    node.setAttribute('x1', x1); node.setAttribute('y1', y1);
    node.setAttribute('x2', x2); node.setAttribute('y2', y2);
  }

  function setCircle(node, x, y) {
    if (!node) return;
    node.setAttribute('cx', x); node.setAttribute('cy', y);
  }

  function updatePiston(group, x1, y1, x2, y2) {
    if (!group.classList.contains('viewer-piston')) return;
    const fidelity = window.OpusStaticArmFidelity;
    if (fidelity?.applyPistonGeometry) fidelity.applyPistonGeometry(group, x1, y1, x2, y2);
  }

  function applyArmState(state, duration) {
    const group = root.querySelector(`[data-part-id="${CSS.escape(state.partId)}"]`);
    if (!group || !group.classList.contains('viewer-arm')) return;
    const targetBranches = branchGeometry(state);
    const base = group.querySelector('[data-arm-base]');
    const baseShadow = group.querySelector('.viewer-arm-base-shadow');
    const hub = group.querySelector(':scope > circle:last-of-type');
    const previous = activeAnimations.get(state.partId);
    if (previous) cancelAnimationFrame(previous);

    const starts = targetBranches.map((target) => {
      const shaft = group.querySelector(`[data-arm-shaft="${target.branchIndex}"]`);
      const shadow = group.querySelector(`[data-arm-shadow="${target.branchIndex}"]`);
      const tip = group.querySelector(`[data-arm-tip="${target.branchIndex}"]`);
      const grip = group.querySelector(`[data-arm-grip="${target.branchIndex}"]`);
      return { target, shaft, shadow, tip, grip,
        x1: numberAttr(shaft, 'x1', target.x1), y1: numberAttr(shaft, 'y1', target.y1),
        x2: numberAttr(shaft, 'x2', target.x2), y2: numberAttr(shaft, 'y2', target.y2) };
    }).filter((item) => item.shaft && item.tip);

    const baseTarget = targetBranches[0] || { x1: 0, y1: 0 };
    const baseStart = { x: numberAttr(base, 'cx', baseTarget.x1), y: numberAttr(base, 'cy', baseTarget.y1) };
    const started = performance.now();

    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const t = core.easeOutCubic(raw);
      const mix = (a, b) => a + (b - a) * t;
      let pistonGeometry = null;
      for (const item of starts) {
        const { target, shaft, shadow, tip, grip } = item;
        const x1 = mix(item.x1, target.x1), y1 = mix(item.y1, target.y1);
        const x2 = mix(item.x2, target.x2), y2 = mix(item.y2, target.y2);
        setLine(shadow, x1, y1, x2, y2); setLine(shaft, x1, y1, x2, y2);
        setCircle(tip, x2, y2); setCircle(grip, x2, y2);
        if (target.branchIndex === 0) pistonGeometry = { x1, y1, x2, y2 };
      }
      if (pistonGeometry) updatePiston(group, pistonGeometry.x1, pistonGeometry.y1, pistonGeometry.x2, pistonGeometry.y2);
      const baseX = mix(baseStart.x, baseTarget.x1), baseY = mix(baseStart.y, baseTarget.y1);
      setCircle(baseShadow, baseX, baseY); setCircle(base, baseX, baseY); setCircle(hub, baseX, baseY);
      group.classList.toggle('replay-grabbing', Boolean(state.grabbing));
      group.dataset.replayRotation = String(state.rotation);
      group.dataset.replayLength = String(state.length || state.baseLength || 1);
      group.dataset.replayHeldCount = String((state.heldMoleculeIds || []).length);
      if (raw < 1) activeAnimations.set(state.partId, requestAnimationFrame(tick));
      else activeAnimations.delete(state.partId);
    };
    activeAnimations.set(state.partId, requestAnimationFrame(tick));
  }

  root.addEventListener('opus:replayframe', (event) => {
    const duration = Number(event.detail?.animationDuration ?? 180);
    const frame = event.detail?.scene?.timeline?.frame || event.detail?.frame || null;
    const seen = new Set();
    for (const state of frame?.armStates || frame?.arms || []) {
      seen.add(state.partId); applyArmState(state, duration);
    }
    root.querySelectorAll('.viewer-arm').forEach((group) => {
      if (!seen.has(group.dataset.partId)) group.classList.remove('replay-grabbing');
    });
  });

  window.addEventListener('opus:analysisready', () => {
    for (const frame of activeAnimations.values()) cancelAnimationFrame(frame);
    activeAnimations.clear();
  });
})();
