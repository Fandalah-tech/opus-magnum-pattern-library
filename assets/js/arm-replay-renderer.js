(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const directions = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];
  const activeAnimations = new Map();

  function armGeometry(state) {
    const origin = state.origin || [0, 0];
    const direction = directions[((Number(state.rotation) % 6) + 6) % 6];
    const length = Math.max(1, Number(state.length || 1));
    const tip = [origin[0] + direction[0] * length, origin[1] + direction[1] * length];
    const [x1, y1] = axialToPixel(origin);
    const [x2, y2] = axialToPixel(tip);
    return { x1, y1, x2, y2 };
  }

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

    const target = armGeometry(state);
    const start = {
      x1: numberAttr(shaft, 'x1', target.x1), y1: numberAttr(shaft, 'y1', target.y1),
      x2: numberAttr(shaft, 'x2', target.x2), y2: numberAttr(shaft, 'y2', target.y2),
    };
    const prior = activeAnimations.get(state.partId);
    if (prior) cancelAnimationFrame(prior);
    const started = performance.now();

    const frame = (now) => {
      const raw = Math.min(1, (now - started) / duration);
      const t = 1 - Math.pow(1 - raw, 3);
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
