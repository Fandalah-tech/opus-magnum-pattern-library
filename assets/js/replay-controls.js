(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root) return;
  const play = root.querySelector('[data-replay-play]');
  const previous = root.querySelector('[data-replay-previous]');
  const next = root.querySelector('[data-replay-next]');
  const range = root.querySelector('[data-replay-range]');
  const cycleLabel = root.querySelector('[data-replay-cycle]');
  const speed = root.querySelector('[data-replay-speed]');
  const note = root.querySelector('[data-replay-note]');
  let trace = null;
  let frameIndex = 0;
  let timer = null;

  const stop = () => {
    if (timer) window.clearInterval(timer);
    timer = null;
    play.dataset.state = 'paused';
    play.textContent = 'Play';
  };

  const renderFrame = () => {
    if (!trace?.frames?.length) return;
    frameIndex = Math.max(0, Math.min(trace.frames.length - 1, frameIndex));
    const frame = trace.frames[frameIndex];
    range.value = String(frameIndex);
    cycleLabel.textContent = `Cycle ${frame.cycle + 1} / ${trace.summary.cycleCount}`;
    const active = new Map((frame.events || []).map((event) => [event.partId, event.instruction]));
    root.querySelectorAll('[data-part-id]').forEach((node) => {
      const instruction = active.get(node.dataset.partId);
      node.classList.toggle('replay-active', Boolean(instruction));
      if (instruction) node.dataset.replayInstruction = instruction;
      else delete node.dataset.replayInstruction;
    });
    root.dispatchEvent(new CustomEvent('opus:replayframe', { detail: { frame, trace } }));
  };

  const step = (delta) => {
    if (!trace?.frames?.length) return;
    frameIndex = Math.max(0, Math.min(trace.frames.length - 1, frameIndex + delta));
    renderFrame();
    if (frameIndex === trace.frames.length - 1) stop();
  };

  play?.addEventListener('click', () => {
    if (!trace?.frames?.length) return;
    if (timer) return stop();
    if (frameIndex >= trace.frames.length - 1) frameIndex = 0;
    play.dataset.state = 'playing';
    play.textContent = 'Pause';
    const interval = () => Math.max(40, 700 / Number(speed.value || 1));
    timer = window.setInterval(() => step(1), interval());
  });
  previous?.addEventListener('click', () => { stop(); step(-1); });
  next?.addEventListener('click', () => { stop(); step(1); });
  range?.addEventListener('input', () => { stop(); frameIndex = Number(range.value); renderFrame(); });
  speed?.addEventListener('change', () => { if (timer) { stop(); play.click(); } });

  window.addEventListener('opus:analysisready', (event) => {
    trace = event.detail.payload?.replay || null;
    frameIndex = 0;
    stop();
    const count = trace?.frames?.length || 0;
    range.max = String(Math.max(0, count - 1));
    range.value = '0';
    [play, previous, next, range, speed].forEach((node) => { if (node) node.disabled = count === 0; });
    if (note) {
      if (trace?.capabilities?.moleculeAnimation) note.textContent = 'Physical replay with molecules.';
      else if (trace?.capabilities?.physicalArmAnimation) note.textContent = 'Kinematic arm replay — molecules, tracks and collisions are not available yet.';
      else note.textContent = 'Program replay preview — physical states are not available yet.';
    }
    renderFrame();
  });
})();
