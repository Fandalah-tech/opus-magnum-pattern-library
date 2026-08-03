(() => {
  const API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const puzzleInput = document.querySelector("#puzzle-file");
  const solutionInput = document.querySelector("#solution-file");
  const button = document.querySelector("#analyze-button");
  const status = document.querySelector("#status");
  const results = document.querySelector("#results");

  const byId = (id) => document.getElementById(id);
  const text = (id, value) => { byId(id).textContent = value ?? "—"; };

  function updateFiles() {
    text("puzzle-name", puzzleInput.files[0]?.name || "Choisir un fichier .puzzle");
    text("solution-name", solutionInput.files[0]?.name || "Choisir un fichier .solution");
    button.disabled = !(puzzleInput.files.length && solutionInput.files.length);
    status.textContent = button.disabled ? "Deux fichiers sont requis." : "Prêt à analyser.";
  }

  puzzleInput.addEventListener("change", updateFiles);
  solutionInput.addEventListener("change", updateFiles);

  function renderFacts(graph) {
    const summary = graph.summary || {};
    const items = [
      ["Nœuds", summary.nodeCount],
      ["Relations", summary.edgeCount],
      ["Composantes", summary.componentCount],
      ["Bras", summary.armCount],
    ];
    byId("graph-summary").innerHTML = items.map(([label, value]) => `<dt>${label}</dt><dd>${value ?? "—"}</dd>`).join("");
  }

  function renderParts(solution) {
    const counts = new Map();
    for (const part of solution.parts || []) counts.set(part.type, (counts.get(part.type) || 0) + 1);
    byId("part-summary").innerHTML = [...counts.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([type, count]) => `<span>${type} × ${count}</span>`).join("") || "<span>Aucune pièce</span>";
    text("part-count", `${solution.parts?.length || 0} pièces`);
  }

  function renderArms(graph) {
    const arms = (graph.nodes || []).filter((node) => node.kind === "arm");
    text("arm-count", `${arms.length} bras`);
    byId("arm-programs").innerHTML = arms.map((arm) => {
      const program = arm.program || {};
      const histogram = Object.entries(program.histogram || {}).map(([name, count]) => `${name} ${count}`).join(" · ");
      return `<div class="arm"><strong><span>${arm.type}</span><span>${program.instructionCount || 0}</span></strong><small>${histogram || "Aucune instruction"}</small></div>`;
    }).join("") || "<p class='hint'>Aucun bras détecté.</p>";
  }

  function renderRelations(graph) {
    const edges = graph.edges || [];
    text("edge-count", `${edges.length} relations`);
    byId("relations").innerHTML = edges.slice(0, 80).map((edge) =>
      `<span>${edge.source} → ${edge.target} · ${edge.type}</span>`
    ).join("") || "<span>Aucune relation candidate</span>";
  }

  function render(payload) {
    const validation = payload.validation;
    const puzzle = payload.puzzle;
    const solution = payload.solution;
    const graph = payload.graph;

    text("solution-title", solution.name || solution.source?.name || "Solution");
    text("puzzle-title", puzzle.name || solution.puzzleFile || "Puzzle");
    const validity = byId("validity");
    validity.textContent = validation.valid ? "VALIDE" : "INVALIDE";
    validity.className = `status-badge ${validation.valid ? "valid" : "invalid"}`;

    const metrics = validation.metrics || solution.metrics || {};
    for (const key of ["cost", "cycles", "area", "instructions"]) text(`metric-${key}`, metrics[key]);

    renderParts(solution);
    renderFacts(graph);
    renderArms(graph);
    renderRelations(graph);
    byId("raw-json").textContent = JSON.stringify(payload, null, 2);
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    results.hidden = true;
    status.textContent = "Analyse en cours…";
    const form = new FormData();
    form.append("puzzle", puzzleInput.files[0]);
    form.append("solution", solutionInput.files[0]);

    try {
      const [validationResponse, graphResponse, puzzleResponse, solutionResponse] = await Promise.all([
        fetch(`${API}/validate`, { method: "POST", body: form }),
        fetch(`${API}/analyze/graph`, { method: "POST", body: (() => { const f = new FormData(); f.append("solution", solutionInput.files[0]); return f; })() }),
        fetch(`${API}/parse/puzzle`, { method: "POST", body: (() => { const f = new FormData(); f.append("puzzle", puzzleInput.files[0]); return f; })() }),
        fetch(`${API}/parse/solution`, { method: "POST", body: (() => { const f = new FormData(); f.append("solution", solutionInput.files[0]); return f; })() }),
      ]);
      const responses = [validationResponse, graphResponse, puzzleResponse, solutionResponse];
      if (responses.some((response) => !response.ok)) {
        const failed = responses.find((response) => !response.ok);
        throw new Error(`API ${failed.status}: ${await failed.text()}`);
      }
      const [validation, graph, puzzle, solution] = await Promise.all(responses.map((response) => response.json()));
      render({ validation, graph, puzzle, solution });
      status.textContent = "Analyse terminée.";
    } catch (error) {
      console.error(error);
      status.textContent = `Échec : ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
})();
