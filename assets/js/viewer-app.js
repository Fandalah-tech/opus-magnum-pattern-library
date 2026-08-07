(() => {
  const byId = id => document.getElementById(id);
  const puzzleInput = byId('viewer-puzzle-file');
  const solutionInput = byId('viewer-solution-file');
  const analyzeButton = byId('viewer-analyze');
  const status = byId('viewer-status');
  const result = byId('viewer-result');
  const metricKeys = ['cycles','cost','area','instructions'];
  const params = new URLSearchParams(location.search);
  const fixtureName = params.get('fixture') || (params.has('demo') ? 'demo' : '');
  const FIXTURES = {
    demo: 'data/viewer-demo-payload.json',
    arms: 'data/viewer-arm-gallery-payload.json',
    pieces: 'data/viewer-piece-gallery-payload.json'
  };

  function updateReady() {
    const ready = Boolean(puzzleInput?.files?.length && solutionInput?.files?.length);
    if (analyzeButton) analyzeButton.disabled = !ready;
    if (status && !fixtureName && !params.has('pair')) {
      status.textContent = ready ? 'Ready to render.' : 'Choose a matching .puzzle and .solution file.';
    }
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

  function renderMachine(payload) {
    renderSummary(payload);
    requestAnimationFrame(() => window.OpusViewerRuntime.renderPayload(payload, '#solution-viewer'));
  }

  async function analyzeFiles(puzzleFile, solutionFile, options = {}) {
    if (!puzzleFile || !solutionFile) throw new Error('Puzzle and solution files are required');
    status.textContent = 'Analyzing and rendering…';
    const payload = await window.OpusViewerRuntime.analyzeFiles(
      puzzleFile,
      solutionFile,
      { root: '#solution-viewer', render: false, signal: options.signal }
    );
    renderMachine(payload);
    if (options.save !== false && window.OpusPairLibrary?.save) {
      try { await window.OpusPairLibrary.save(puzzleFile, solutionFile); }
      catch (error) { console.warn('Unable to save local viewer pair', error); }
    }
    status.textContent = 'Render complete.';
    return payload;
  }

  async function analyze() {
    analyzeButton.disabled = true;
    try {
      await analyzeFiles(puzzleInput.files[0], solutionInput.files[0]);
    } catch (error) {
      console.error(error);
      status.textContent = `Failed: ${error.message}`;
    } finally {
      updateReady();
    }
  }

  async function loadFixture() {
    if (!fixtureName) return;
    const fixtureUrl = FIXTURES[fixtureName];
    if (!fixtureUrl) {
      status.textContent = `Unknown renderer fixture: ${fixtureName}`;
      document.body.dataset.viewerDemoReady = 'false';
      return;
    }
    status.textContent = `Loading renderer fixture · ${fixtureName}…`;
    try {
      const response = await fetch(fixtureUrl, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Fixture payload → ${response.status}`);
      const payload = await response.json();
      renderMachine(payload);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      status.textContent = `Fixture render complete · ${fixtureName}.`;
      document.body.dataset.viewerFixture = fixtureName;
      document.body.dataset.viewerDemoReady = 'true';
    } catch (error) {
      console.error(error);
      status.textContent = `Fixture failed: ${error.message}`;
      document.body.dataset.viewerDemoReady = 'false';
    }
  }

  window.OpusViewerApp = Object.freeze({ analyzeFiles, renderMachine, updateReady });
  puzzleInput?.addEventListener('change', updateReady);
  solutionInput?.addEventListener('change', updateReady);
  analyzeButton?.addEventListener('click', analyze);
  window.addEventListener('resize', () => window.OpusViewerRuntime?.fit?.('#solution-viewer'));
  updateReady();
  loadFixture();
})();
