(() => {
  if (window.OpusViewerRuntime) return;

  const DEFAULT_API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const ANALYZE_ENDPOINT = "/api/v1/analyze";
  const instances = new WeakMap();

  function resolveRoot(rootOrSelector = "#solution-viewer") {
    if (typeof rootOrSelector === "string") return document.querySelector(rootOrSelector);
    return rootOrSelector || null;
  }

  function mount(rootOrSelector = "#solution-viewer") {
    const root = resolveRoot(rootOrSelector);
    if (!root) throw new Error("Opus viewer root not found");
    if (!window.OpusSolutionViewer?.create) throw new Error("OpusSolutionViewer must load before OpusViewerRuntime");
    if (instances.has(root)) return instances.get(root);
    const viewer = window.OpusSolutionViewer.create(root);
    instances.set(root, viewer);
    return viewer;
  }

  function renderPayload(payload, rootOrSelector = "#solution-viewer") {
    if (!payload?.solution) throw new Error("Analysis payload does not contain a solution");
    const viewer = mount(rootOrSelector);
    viewer.render(payload.solution, payload.graph, payload.puzzle, payload.replay);
    window.dispatchEvent(new CustomEvent("opus:analysisready", { detail: { payload, viewer } }));
    return viewer;
  }

  async function analyzeFiles(puzzleFile, solutionFile, options = {}) {
    if (!puzzleFile || !solutionFile) throw new Error("Puzzle and solution files are required");
    const api = String(options.api || DEFAULT_API).replace(/\/$/, "");
    const endpoint = options.endpoint || ANALYZE_ENDPOINT;
    const form = new FormData();
    form.append("puzzle", puzzleFile);
    form.append("solution", solutionFile);
    const response = await fetch(`${api}${endpoint}`, { method: "POST", body: form, signal: options.signal });
    if (!response.ok) throw new Error(`POST ${endpoint} → ${response.status}: ${await response.text()}`);
    const payload = await response.json();
    if (options.render !== false) renderPayload(payload, options.root || "#solution-viewer");
    return payload;
  }

  function fit(rootOrSelector = "#solution-viewer") {
    const root = resolveRoot(rootOrSelector);
    const viewer = root ? instances.get(root) : null;
    viewer?.fit?.();
  }

  window.OpusViewerRuntime = Object.freeze({
    DEFAULT_API,
    ANALYZE_ENDPOINT,
    mount,
    renderPayload,
    analyzeFiles,
    fit
  });
})();
