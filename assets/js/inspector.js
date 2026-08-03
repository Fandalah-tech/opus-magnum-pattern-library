(() => {
  const API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const puzzleInput = document.querySelector("#puzzle-file");
  const solutionInput = document.querySelector("#solution-file");
  const button = document.querySelector("#analyze-button");
  const status = document.querySelector("#status");
  const results = document.querySelector("#results");

  const byId = (id) => document.getElementById(id);
  const text = (id, value) => { byId(id).textContent = value ?? "—"; };
  const solutionForm = () => {
    const form = new FormData();
    form.append("solution", solutionInput.files[0]);
    return form;
  };

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

  function renderTimeline(timeline) {
    const summary = timeline.summary || {};
    text("timeline-horizon", `${summary.horizon ?? 0} cycles analysés`);
    const facts = [
      ["Cycles actifs", summary.activeCycleCount],
      ["Cycles globalement inactifs", summary.globalIdleCycles],
      ["Pic de parallélisme", summary.peakParallelArms],
      ["Parallélisme moyen", summary.averageParallelArms],
    ];
    byId("timeline-facts").innerHTML = facts.map(([label, value]) => `<div><small>${label}</small><strong>${value ?? "—"}</strong></div>`).join("");
    byId("timeline-arms").innerHTML = (timeline.arms || []).map((arm) => {
      const pct = Math.max(0, Math.min(100, Math.round((arm.utilization || 0) * 100)));
      const label = `${arm.type}${arm.armNumber !== undefined ? ` #${arm.armNumber}` : ""}`;
      return `<div class="timeline-row"><div class="timeline-label"><strong>${label}</strong><small>${arm.actionCount} actions · période ${arm.period}</small></div><div class="timeline-track"><span style="width:${pct}%"></span></div><b>${pct}%</b></div>`;
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
    const { validation, puzzle, solution, graph, timeline } = payload;
    text("solution-title", solution.name || solution.source?.name || "Solution");
    text("puzzle-title", puzzle.name || solution.puzzleFile || "Puzzle");
    const validity = byId("validity");
    validity.textContent = validation.valid ? "VALIDE" : "INVALIDE";
    validity.className = `status-badge ${validation.valid ? "valid" : "invalid"}`;

    const validatorMetrics = validation.metrics || {};
    const declaredMetrics = solution.metrics || {};
    for (const key of ["cost", "cycles", "area", "instructions"]) {
      text(`metric-${key}`, validatorMetrics[key] ?? declaredMetrics[key]);
    }

    renderParts(solution);
    renderFacts(graph);
    renderArms(graph);
    renderTimeline(timeline);
    renderRelations(graph);
    byId("raw-json").textContent = JSON.stringify(payload, null, 2);
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    results.hidden = true;
    status.textContent = "Analyse en cours…";
    const validationForm = new FormData();
    validationForm.append("puzzle", puzzleInput.files[0]);
    validationForm.append("solution", solutionInput.files[0]);
    const puzzleForm = new FormData();
    puzzleForm.append("puzzle", puzzleInput.files[0]);

    try {
      const responses = await Promise.all([
        fetch(`${API}/validate`, { method: "POST", body: validationForm }),
        fetch(`${API}/analyze/graph`, { method: "POST", body: solutionForm() }),
        fetch(`${API}/analyze/timeline`, { method: "POST", body: solutionForm() }),
        fetch(`${API}/parse/puzzle`, { method: "POST", body: puzzleForm }),
        fetch(`${API}/parse/solution`, { method: "POST", body: solutionForm() }),
      ]);
      if (responses.some((response) => !response.ok)) {
        const failed = responses.find((response) => !response.ok);
        throw new Error(`API ${failed.status}: ${await failed.text()}`);
      }
      const [validation, graph, timeline, puzzle, solution] = await Promise.all(responses.map((response) => response.json()));
      render({ validation, graph, timeline, puzzle, solution });
      status.textContent = "Analyse terminée.";
    } catch (error) {
      console.error(error);
      status.textContent = `Échec : ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
})();
