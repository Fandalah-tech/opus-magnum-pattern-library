(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const core = window.OpusRendererCore;
  if (!core) throw new Error('OpusRendererCore must load before arm-replay-renderer.js');
  const activeAnimations = new Map();

  function numberAttr(node, name, fallback) {
    const value = Number(node?.getAttribute(name));
    return Number.isFinite(value) ? value : fallback;
  }

  function animateArm(state, duration = 360) {
    const group = root.querySelector(`[data-part-id="${CSS.escape(state.partId)}"]`);
    if (!group) return;
    const shaft = [...group.querySelectorAll('line')].find((node) => Number(node.getAttribute('stroke-width')) >= 7);
    const tip = [...group.querySelectorAll('circle')].find((node) => Number(node.getAttribute('r')) === 10);
    if (!shaft || !tip) return;
    const target = core.armGeometry(state);
    const start = {
      x1: numberAttr(shaft, 'x1', target.x1), y1: numberAttr(shaft, 'y1', target.y1),
      x2: numberAttr(shaft, 'x2', target.x2), y2: numberAttr(shaft, 'y2', target.y2),
    };
    const prior = activeAnimations.get(state.partId);
    if (prior) cancelAnimationFrame(prior);
    const started = performance.now();
    const frame = (now) => {
      const raw = Math.min(1, (now - started) / duration);
      const t = core.easeOutCubic(raw);
      const value = (a, b) => a + (b - a) * t;
      const x1 = value(start.x1, target.x1), y1 = value(start.y1, target.y1);
      const x2 = value(start.x2, target.x2), y2 = value(start.y2, target.y2);
      shaft.setAttribute('x1', x1); shaft.setAttribute('y1', y1);
      shaft.setAttribute('x2', x2); shaft.setAttribute('y2', y2);
      tip.setAttribute('cx', x2); tip.setAttribute('cy', y2);
      group.classList.toggle('replay-grabbing', Boolean(state.grabbing));
      group.dataset.replayRotation = String(state.rotation);
      group.dataset.replayLength = String(state.length);
      if (raw < 1) activeAnimations.set(state.partId, requestAnimationFrame(frame));
      else activeAnimations.delete(state.partId);
    };
    activeAnimations.set(state.partId, requestAnimationFrame(frame));
  }

  root.addEventListener('opus:replayframe', (event) => {
    const states = event.detail?.frame?.armStates || [];
    const playing = root.querySelector('[data-replay-play]')?.dataset.state === 'playing';
    const duration = playing ? 420 : 120;
    states.forEach((state) => animateArm(state, duration));
  });
})();
