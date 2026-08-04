(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const directions = window.OpusGeometry?.DIRECTIONS || [[1,0],[0,1],[-1,1],[-1,0],[0,-1],[1,-1]];
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];

  function applyArmState(state) {
    const group = root.querySelector(`[data-part-id="${CSS.escape(state.partId)}"]`);
    if (!group || !group.classList.contains('viewer-arm')) return;
    const circles = group.querySelectorAll(':scope > circle');
    const shaft = group.querySelector(':scope > line');
    if (!shaft || circles.length < 2) return;

    const origin = state.origin || [0, 0];
    const direction = directions[((Number(state.rotation) % 6) + 6) % 6];
    const length = Math.max(1, Number(state.length || state.baseLength || 1));
    const target = [origin[0] + direction[0] * length, origin[1] + direction[1] * length];
    const [x, y] = axialToPixel(origin);
    const [ex, ey] = axialToPixel(target);

    shaft.setAttribute('x1', x); shaft.setAttribute('y1', y);
    shaft.setAttribute('x2', ex); shaft.setAttribute('y2', ey);
    circles[0].setAttribute('cx', x); circles[0].setAttribute('cy', y);
    circles[1].setAttribute('cx', ex); circles[1].setAttribute('cy', ey);
    group.classList.toggle('replay-grabbing', Boolean(state.grabbing));
    group.dataset.replayRotation = String(state.rotation);
    group.dataset.replayLength = String(length);
  }

  root.addEventListener('opus:replayframe', (event) => {
    for (const state of event.detail.frame?.armStates || []) applyArmState(state);
  });
})();
