(() => {
  if (window.OpusViewerRuntime) return;

  const DEFAULT_API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const ANALYZE_ENDPOINT = "/api/v1/analyze";
  const instances = new WeakMap();
  const scenes = new WeakMap();

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

  function buildScene(payload, options = {}) {
    if (!window.OpusScene?.build) throw new Error("OpusScene must load before OpusViewerRuntime");
    return window.OpusScene.build(payload, options);
  }

  function renderScene(scene, rootOrSelector = "#solution-viewer") {
    if (!scene?.source?.solution) throw new Error("Invalid Opus scene");
    const root = resolveRoot(rootOrSelector);
    const viewer = mount(root);
    scenes.set(root, scene);
    viewer.render(scene.source.solution, scene.source.graph, scene.source.puzzle, scene.source.replay);
    window.OpusStaticArmFidelity?.apply?.(viewer, scene.source.solution);
    window.dispatchEvent(new CustomEvent("opus:sceneready", { detail: { scene, viewer } }));
    window.dispatchEvent(new CustomEvent("opus:analysisready", { detail: { payload: scene.source, scene, viewer } }));
    return viewer;
  }

  function renderPayload(payload, rootOrSelector = "#solution-viewer") {
    if (!payload?.solution) throw new Error("Analysis payload does not contain a solution");
    return renderScene(buildScene(payload), rootOrSelector);
  }

  async function loadPayload(url, options = {}) {
    const response = await fetch(url, { cache: options.cache || "no-store", signal: options.signal });
    if (!response.ok) throw new Error(`GET payload → ${response.status}: ${await response.text()}`);
    const payload = await response.json();
    if (options.render !== false) renderPayload(payload, options.root || "#solution-viewer");
    return payload;
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

  function currentScene(rootOrSelector = "#solution-viewer") {
    const root = resolveRoot(rootOrSelector);
    return root ? scenes.get(root) || null : null;
  }

  function sceneAtFrame(frameIndex, rootOrSelector = "#solution-viewer") {
    const scene = currentScene(rootOrSelector);
    return scene && window.OpusScene?.atFrame ? window.OpusScene.atFrame(scene, frameIndex) : scene;
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
    buildScene,
    renderScene,
    renderPayload,
    loadPayload,
    analyzeFiles,
    currentScene,
    sceneAtFrame,
    fit
  });
})();
