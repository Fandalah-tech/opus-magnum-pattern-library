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
  let scene = null;
  let frameIndex = 0;
  let timer = null;
  let initialFrameRequest = null;
  let playing = false;

  const playbackRate = () => Math.max(.25, Number(speed?.value || 1));
  const frameInterval = () => Math.max(80, 700 / playbackRate());
  const animationDuration = (manual = false) => manual
    ? 170
    : Math.max(65, Math.min(620, frameInterval() * .78));

  const clearTimer = () => {
    if (timer) window.clearTimeout(timer);
    timer = null;
  };

  const clearInitialFrame = () => {
    if (initialFrameRequest) cancelAnimationFrame(initialFrameRequest);
    initialFrameRequest = null;
  };

  const stop = () => {
    clearTimer();
    playing = false;
    play.dataset.state = 'paused';
    play.textContent = 'Play';
  };

  const renderFrame = ({ manual = false } = {}) => {
    if (!trace?.frames?.length) return;
    frameIndex = Math.max(0, Math.min(trace.frames.length - 1, frameIndex));
    const frame = trace.frames[frameIndex];
    range.value = String(frameIndex);
    cycleLabel.textContent = frame.phaseLabel === 'initial'
      ? `Initial state · 0 / ${trace.summary.cycleCount}`
      : `Cycle ${frame.displayCycle ?? frame.cycle + 1} / ${trace.summary.cycleCount}`;
    const active = new Map((frame.events || []).map((event) => [event.partId, event.instruction]));
    root.querySelectorAll('[data-part-id]').forEach((node) => {
      const instruction = active.get(node.dataset.partId);
      node.classList.toggle('replay-active', Boolean(instruction));
      if (instruction) node.dataset.replayInstruction = instruction;
      else delete node.dataset.replayInstruction;
    });
    const rate = playbackRate();
    const duration = animationDuration(manual);
    root.dataset.replaySpeed = String(rate);
    const frameScene = scene && window.OpusScene?.atFrame ? window.OpusScene.atFrame(scene, frameIndex) : scene;
    root.dispatchEvent(new CustomEvent('opus:replayframe', {
      detail: {
        frame,
        scene: frameScene,
        trace,
        playbackRate: rate,
        animationDuration: duration,
        isPlaying: playing,
        manual
      }
    }));
  };

  const scheduleNext = () => {
    clearTimer();
    if (!playing || !trace?.frames?.length) return;
    timer = window.setTimeout(() => {
      timer = null;
      if (!playing) return;
      if (frameIndex >= trace.frames.length - 1) {
        stop();
        return;
      }
      frameIndex += 1;
      renderFrame({ manual: false });
      if (frameIndex >= trace.frames.length - 1) stop();
      else scheduleNext();
    }, frameInterval());
  };

  const step = (delta) => {
    if (!trace?.frames?.length) return;
    clearInitialFrame();
    frameIndex = Math.max(0, Math.min(trace.frames.length - 1, frameIndex + delta));
    renderFrame({ manual: true });
  };

  play?.addEventListener('click', () => {
    if (!trace?.frames?.length) return;
    clearInitialFrame();
    if (playing) {
      stop();
      return;
    }
    if (frameIndex >= trace.frames.length - 1) frameIndex = 0;
    playing = true;
    play.dataset.state = 'playing';
    play.textContent = 'Pause';
    renderFrame({ manual: false });
    scheduleNext();
  });
  previous?.addEventListener('click', () => { stop(); step(-1); });
  next?.addEventListener('click', () => { stop(); step(1); });
  range?.addEventListener('input', () => {
    stop();
    clearInitialFrame();
    frameIndex = Number(range.value);
    renderFrame({ manual: true });
  });
  speed?.addEventListener('change', () => {
    root.dataset.replaySpeed = String(playbackRate());
    if (playing) scheduleNext();
  });

  window.addEventListener('opus:sceneready', (event) => {
    scene = event.detail.scene || null;
    const timeline = scene?.timeline || null;
    trace = timeline ? {
      frames: timeline.frames || [],
      summary: { cycleCount: Number(timeline.cycleCount || 0) },
      capabilities: { ...(timeline.capabilities || {}) }
    } : null;
    frameIndex = 0;
    stop();
    clearInitialFrame();
    const count = trace?.frames?.length || 0;
    range.max = String(Math.max(0, count - 1));
    range.value = '0';
    root.dataset.replaySpeed = String(playbackRate());
    [play, previous, next, range, speed].forEach((node) => { if (node) node.disabled = count === 0; });
    if (note) {
      if (trace?.capabilities?.multiBranchGrab) note.textContent = 'Physical replay with molecules and multi-branch arms.';
      else if (trace?.capabilities?.moleculeAnimation) note.textContent = 'Physical replay with molecules.';
      else if (trace?.capabilities?.physicalArmAnimation) note.textContent = 'Kinematic arm replay — molecules, tracks and collisions are not available yet.';
      else note.textContent = 'Program replay preview — physical states are not available yet.';
    }
    // OpusViewerRuntime emits sceneready before analysisready. Defer the first
    // frame one paint so legacy analysisready listeners can finish resetting.
    if (count > 0) {
      initialFrameRequest = requestAnimationFrame(() => {
        initialFrameRequest = null;
        renderFrame({ manual: true });
      });
    }
  });
})();
