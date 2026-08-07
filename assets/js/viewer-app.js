(() => {
  const byId = id => document.getElementById(id);
  const puzzleInput = byId('viewer-puzzle-file');
  const solutionInput = byId('viewer-solution-file');
  const analyzeButton = byId('viewer-analyze');
  const status = byId('viewer-status');
  const result = byId('viewer-result');
  const metricKeys = ['cycles','cost','area','instructions'];

  function updateReady() {
    const ready = Boolean(puzzleInput?.files?.length && solutionInput?.files?.length);
    if (analyzeButton) analyzeButton.disabled = !ready;
    if (status) status.textContent = ready ? 'Ready to render.' : 'Choose a matching .puzzle and .solution file.';
  }

  function renderSummary(payload) {
    const solution = payload?.solution || {};
    const puzzle = payload?.puzzle || {};
    const validation = payload?.validation || {};
    const metrics = { ...(solution.metrics || {}), ...(validation.metrics || {}) };
    byId('viewer-solution-title').textContent = solution.name || solution.source?.name || 'Solution';
    byId('viewer-puzzle-title').textContent = puzzle.name || solution.puzzleFile || 'Puzzle';
    for (const key of metricKeys) byId(`viewer-metric-${key}`).textContent = metrics[key] ?? '—';
    const badge = byId('viewer-validity');
    const state = validation.status || (validation.valid === true ? 'valid' : validation.valid === false ? 'invalid' : 'unknown');
    badge.textContent = state;
    badge.dataset.state = state;
    result.hidden = false;
  }

  async function analyze() {
    analyzeButton.disabled = true;
    status.textContent = 'Analyzing and rendering…';
    try {
      const payload = await window.OpusViewerRuntime.analyzeFiles(
        puzzleInput.files[0],
        solutionInput.files[0],
        { root: '#solution-viewer' }
      );
      renderSummary(payload);
      status.textContent = 'Render complete.';
    } catch (error) {
      console.error(error);
      status.textContent = `Failed: ${error.message}`;
    } finally {
      updateReady();
    }
  }

  puzzleInput?.addEventListener('change', updateReady);
  solutionInput?.addEventListener('change', updateReady);
  analyzeButton?.addEventListener('click', analyze);
  window.addEventListener('resize', () => window.OpusViewerRuntime?.fit?.('#solution-viewer'));
  updateReady();
})();
