(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;

  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const directions = window.OpusGeometry?.DIRECTIONS || [[1,0],[0,1],[-1,1],[-1,0],[0,-1],[1,-1]];
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const activeAnimations = new Map();

  function geometry(state) {
    const origin = state.origin || [0, 0];
    const direction = directions[((Number(state.rotation) % 6) + 6) % 6];
    const length = Math.max(1, Number(state.length || state.baseLength || 1));
    const target = [origin[0] + direction[0] * length, origin[1] + direction[1] * length];
    const [x1, y1] = axialToPixel(origin);
    const [x2, y2] = axialToPixel(target);
    return { x1, y1, x2, y2, length };
  }

  function attr(node, name, fallback) {
    const value = Number(node?.getAttribute(name));
    return Number.isFinite(value) ? value : fallback;
  }

  function applyArmState(state, duration) {
    const group = root.querySelector(`[data-part-id="${CSS.escape(state.partId)}"]`);
    if (!group || !group.classList.contains('viewer-arm')) return;
    const circles = group.querySelectorAll(':scope > circle');
    const shaft = group.querySelector(':scope > line');
    if (!shaft || circles.length < 2) return;

    const target = geometry(state);
    const start = {
      x1: attr(shaft, 'x1', target.x1), y1: attr(shaft, 'y1', target.y1),
      x2: attr(shaft, 'x2', target.x2), y2: attr(shaft, 'y2', target.y2),
    };
    const previous = activeAnimations.get(state.partId);
    if (previous) cancelAnimationFrame(previous);
    const started = performance.now();

    const tick = (now) => {
      const raw = duration <= 0 ? 1 : Math.min(1, (now - started) / duration);
      const t = 1 - Math.pow(1 - raw, 3);
      const mix = (a, b) => a + (b - a) * t;
      const x1 = mix(start.x1, target.x1), y1 = mix(start.y1, target.y1);
      const x2 = mix(start.x2, target.x2), y2 = mix(start.y2, target.y2);
      shaft.setAttribute('x1', x1); shaft.setAttribute('y1', y1);
      shaft.setAttribute('x2', x2); shaft.setAttribute('y2', y2);
      circles[0].setAttribute('cx', x1); circles[0].setAttribute('cy', y1);
      circles[1].setAttribute('cx', x2); circles[1].setAttribute('cy', y2);
      group.classList.toggle('replay-grabbing', Boolean(state.grabbing));
      group.dataset.replayRotation = String(state.rotation);
      group.dataset.replayLength = String(target.length);
      if (raw < 1) activeAnimations.set(state.partId, requestAnimationFrame(tick));
      else activeAnimations.delete(state.partId);
    };
    activeAnimations.set(state.partId, requestAnimationFrame(tick));
  }

  root.addEventListener('opus:replayframe', (event) => {
    const playing = root.querySelector('[data-replay-play]')?.dataset.state === 'playing';
    const duration = playing ? 420 : 140;
    for (const state of event.detail.frame?.armStates || []) applyArmState(state, duration);
  });
})();
