(() => {
  const puzzleInput = document.querySelector('#diff-puzzle-file');
  const beforeInput = document.querySelector('#diff-solution-before');
  const afterInput = document.querySelector('#diff-solution-after');
  const button = document.querySelector('#diff-analyze');
  const status = document.querySelector('#diff-status');
  const result = document.querySelector('#diff-result');
  const svg = document.querySelector('#diff-svg');
  const world = svg?.querySelector('[data-diff-world]');
  const summary = document.querySelector('#diff-summary');
  const metrics = document.querySelector('#diff-metrics');
  if (!puzzleInput || !beforeInput || !afterInput || !button || !status || !result || !svg || !world) return;

  const runtime = window.OpusViewerRuntime;
  const sceneDiff = window.OpusSceneDiff;
  const svgRenderer = window.OpusSvgRenderer;
  const diffOverlay = window.OpusSvgDiffOverlay;
  if (!runtime || !sceneDiff || !svgRenderer || !diffOverlay) {
    throw new Error('Scene Diff Lab requires OpusViewerRuntime, OpusSceneDiff, OpusSvgRenderer and OpusSvgDiffOverlay');
  }

  const allFilesReady = () => Boolean(puzzleInput.files[0] && beforeInput.files[0] && afterInput.files[0]);

  function updateReadyState() {
    button.disabled = !allFilesReady();
    status.textContent = button.disabled
      ? 'Choose one puzzle and two solutions to compare.'
      : 'Ready to compare Solution A → Solution B.';
  }

  function deltaText(metric) {
    if (!metric) return '—';
    const before = metric.before ?? '—';
    const after = metric.after ?? '—';
    const delta = metric.delta;
    const deltaLabel = Number.isFinite(delta) ? `${delta > 0 ? '+' : ''}${delta}` : '—';
    return `${before} → ${after} (${deltaLabel})`;
  }

  function renderSummary(diff) {
    const s = diff.summary || {};
    summary.innerHTML = [
      ['Added', s.addedParts],
      ['Removed', s.removedParts],
      ['Moved', s.movedParts],
      ['Changed', s.changedParts],
      ['Added hexes', s.addedCells],
      ['Removed hexes', s.removedCells]
    ].map(([label, value]) => `<article><small>${label}</small><strong>${value ?? 0}</strong></article>`).join('');

    const preferred = ['cycles', 'cost', 'area', 'instructions'];
    const keys = [...preferred.filter(key => diff.metrics?.[key]), ...Object.keys(diff.metrics || {}).filter(key => !preferred.includes(key))];
    metrics.innerHTML = keys.map(key => `<div><small>${key}</small><strong>${deltaText(diff.metrics[key])}</strong></div>`).join('') || '<p class="hint">No numeric metric delta available.</p>';
  }

  function fitWorld() {
    requestAnimationFrame(() => {
      let box;
      try { box = world.getBBox(); } catch { box = null; }
      if (!box || (!box.width && !box.height)) return;
      const pad = 70;
      svg.setAttribute('viewBox', `${box.x - pad} ${box.y - pad} ${Math.max(1, box.width + pad * 2)} ${Math.max(1, box.height + pad * 2)}`);
    });
  }

  function renderDiff(beforeScene, afterScene) {
    const diff = sceneDiff.diff(beforeScene, afterScene);
    const renderer = svgRenderer.create(world);
    renderer.render(afterScene);
    const overlayLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    overlayLayer.setAttribute('class', 'viewer-layer viewer-layer-scene-diff');
    overlayLayer.setAttribute('data-viewer-layer', 'scene-diff');
    overlayLayer.setAttribute('pointer-events', 'none');
    world.append(overlayLayer);
    diffOverlay.create(overlayLayer).render(diff);
    renderSummary(diff);
    result.hidden = false;
    fitWorld();
    window.__OPUS_SCENE_DIFF__ = diff;
    window.__OPUS_SCENE_DIFF_BEFORE__ = beforeScene;
    window.__OPUS_SCENE_DIFF_AFTER__ = afterScene;
    window.dispatchEvent(new CustomEvent('opus:scenediffready', { detail: { diff, beforeScene, afterScene } }));
    return diff;
  }

  async function compareFiles() {
    button.disabled = true;
    result.hidden = true;
    status.textContent = 'Analyzing Solution A…';
    try {
      const beforePayload = await runtime.analyzeFiles(puzzleInput.files[0], beforeInput.files[0], { render: false });
      status.textContent = 'Analyzing Solution B…';
      const afterPayload = await runtime.analyzeFiles(puzzleInput.files[0], afterInput.files[0], { render: false });
      const beforeScene = runtime.buildScene(beforePayload);
      const afterScene = runtime.buildScene(afterPayload);
      renderDiff(beforeScene, afterScene);
      status.textContent = 'Comparison complete.';
    } catch (error) {
      console.error(error);
      status.textContent = `Comparison failed: ${error.message}`;
    } finally {
      button.disabled = !allFilesReady();
    }
  }

  [puzzleInput, beforeInput, afterInput].forEach(input => input.addEventListener('change', updateReadyState));
  button.addEventListener('click', compareFiles);
  updateReadyState();

  window.OpusSceneDiffLab = Object.freeze({ renderDiff, fitWorld });
})();
