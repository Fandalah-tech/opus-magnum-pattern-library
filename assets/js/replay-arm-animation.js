(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const activeAnimations = new Map();

  function branchGeometry(state) {
    const origin = state.origin || [0, 0];
    const [x1, y1] = axialToPixel(origin);
    const tips = state.tips || [];
    return tips.map((tip, branchIndex) => {
      const [x2, y2] = axialToPixel(tip.position || origin);
      return { branchIndex: tip.branchIndex ?? branchIndex, x1, y1, x2, y2 };
    });
  }

  function numberAttr(node, name, fallback) {
    const value = Number(node?.getAttribute(name));
    return Number.isFinite(value) ? value : fallback;
  }

  function setLine(node, x1, y1, x2, y2) {
    if (!node) return;
    node.setAttribute('x1', x1);
    node.setAttribute('y1', y1);
    node.setAttribute('x2', x2);
    node.setAttribute('y2', y2);
  }

  function setCircle(node, x, y) {
    if (!node) return;
    node.setAttribute('cx', x);
    node.setAttribute('cy', y);
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
      return {
        target, shaft, shadow, tip, grip,
        x1: numberAttr(shaft, 'x1', target.x1),
        y1: numberAttr(shaft, 'y1', target.y1),
        x2: numberAttr(shaft, 'x2', target.x2),
        y2: numberAttr(shaft, 'y2', target.y2)
      };
    }).filter((item) => item.shaft && item.tip);

    const baseTarget = targetBranches[0] || { x1: 0, y1: 0 };
    const baseStart = {
      x: numberAttr(base, 'cx', baseTarget.x1),
      y: numberAttr(base, 'cy', baseTarget.y1)
    };
    const started = performance.now();

    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const t = 1 - Math.pow(1 - raw, 3);
      const mix = (a, b) => a + (b - a) * t;

      for (const item of starts) {
        const { target, shaft, shadow, tip, grip } = item;
        const x1 = mix(item.x1, target.x1);
        const y1 = mix(item.y1, target.y1);
        const x2 = mix(item.x2, target.x2);
        const y2 = mix(item.y2, target.y2);
        setLine(shadow, x1, y1, x2, y2);
        setLine(shaft, x1, y1, x2, y2);
        setCircle(tip, x2, y2);
        setCircle(grip, x2, y2);
      }

      const baseX = mix(baseStart.x, baseTarget.x1);
      const baseY = mix(baseStart.y, baseTarget.y1);
      setCircle(baseShadow, baseX, baseY);
      setCircle(base, baseX, baseY);
      setCircle(hub, baseX, baseY);

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
    const seen = new Set();
    for (const state of event.detail.frame?.armStates || []) {
      seen.add(state.partId);
      applyArmState(state, duration);
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
