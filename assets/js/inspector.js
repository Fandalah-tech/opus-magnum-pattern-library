(() => {
  const API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const i18n = window.OpusI18n;
  const puzzleInput = document.querySelector("#puzzle-file");
  const solutionInput = document.querySelector("#solution-file");
  const button = document.querySelector("#analyze-button");
  const status = document.querySelector("#status");
  const results = document.querySelector("#results");
  const localeSelect = document.querySelector("#locale-select");

  const byId = (id) => document.getElementById(id);
  const text = (id, value) => { byId(id).textContent = value ?? "—"; };
  const t = (key) => i18n.t(key);
  const solutionForm = () => {
    const form = new FormData();
    form.append("solution", solutionInput.files[0]);
    return form;
  };

  function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel)); });
    document.querySelectorAll("[data-i18n-content]").forEach((node) => { node.setAttribute("content", t(node.dataset.i18nContent)); });
    document.documentElement.lang = i18n.locale === "fr" ? "fr-CA" : "en";
    localeSelect.value = i18n.locale;
    updateFiles();
  }

  function updateFiles() {
    text("puzzle-name", puzzleInput.files[0]?.name || t("inspector.choosePuzzle"));
    text("solution-name", solutionInput.files[0]?.name || t("inspector.chooseSolution"));
    button.disabled = !(puzzleInput.files.length && solutionInput.files.length);
    status.textContent = button.disabled ? t("inspector.twoFiles") : t("inspector.ready");
  }

  puzzleInput.addEventListener("change", updateFiles);
  solutionInput.addEventListener("change", updateFiles);
  localeSelect.addEventListener("change", () => i18n.setLocale(localeSelect.value));
  window.addEventListener("opus:localechange", applyTranslations);

  function renderFacts(graph) {
    const summary = graph.summary || {};
    const items = [[t("inspector.nodes"), summary.nodeCount], [t("nav.relations"), summary.edgeCount], [t("inspector.components"), summary.componentCount], [t("inspector.arms"), summary.armCount]];
    byId("graph-summary").innerHTML = items.map(([label, value]) => `<dt>${label}</dt><dd>${value ?? "—"}</dd>`).join("");
  }

  function renderParts(solution) {
    const counts = new Map();
    for (const part of solution.parts || []) counts.set(part.type, (counts.get(part.type) || 0) + 1);
    byId("part-summary").innerHTML = [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([type, count]) => `<span>${type} × ${count}</span>`).join("") || `<span>${t("inspector.noParts")}</span>`;
    text("part-count", `${solution.parts?.length || 0} ${t("inspector.parts")}`);
  }

  function renderArms(graph) {
    const arms = (graph.nodes || []).filter((node) => node.kind === "arm");
    text("arm-count", `${arms.length} ${t("inspector.armCount")}`);
    byId("arm-programs").innerHTML = arms.map((arm) => {
      const program = arm.program || {};
      const histogram = Object.entries(program.histogram || {}).map(([name, count]) => `${name} ${count}`).join(" · ");
      return `<div class="arm"><strong><span>${arm.type}</span><span>${program.instructionCount || 0}</span></strong><small>${histogram || t("inspector.noInstructions")}</small></div>`;
    }).join("") || `<p class='hint'>${t("inspector.noArms")}</p>`;
  }

  function renderPatterns(patterns) {
    const findings = patterns.findings || [];
    text("pattern-count", `${findings.length} ${t("inspector.patternCount")}`);
    byId("pattern-findings").innerHTML = findings.map((finding) => {
      const name = t(`pattern.${finding.id}`);
      const confidence = t(`confidence.${finding.confidence}`);
      const evidenceCount = finding.evidence?.length || 0;
      return `<article class="pattern-finding"><div><strong>${name}</strong><small>${finding.id}</small></div><span class="confidence ${finding.confidence}">${confidence}</span><p>${evidenceCount} ${t("inspector.evidenceItems")}</p></article>`;
    }).join("") || `<p class='hint'>${t("inspector.noPatterns")}</p>`;
  }

  function renderTimeline(timeline) {
    const summary = timeline.summary || {};
    text("timeline-horizon", `${summary.horizon ?? 0} ${t("inspector.cyclesAnalyzed")}`);
    const facts = [[t("inspector.activeCycles"), summary.activeCycleCount], [t("inspector.globalIdle"), summary.globalIdleCycles], [t("inspector.peakParallel"), summary.peakParallelArms], [t("inspector.averageParallel"), summary.averageParallelArms]];
    byId("timeline-facts").innerHTML = facts.map(([label, value]) => `<div><small>${label}</small><strong>${value ?? "—"}</strong></div>`).join("");
    byId("timeline-arms").innerHTML = (timeline.arms || []).map((arm) => {
      const pct = Math.max(0, Math.min(100, Math.round((arm.utilization || 0) * 100)));
      const label = `${arm.type}${arm.armNumber !== undefined ? ` #${arm.armNumber}` : ""}`;
      return `<div class="timeline-row"><div class="timeline-label"><strong>${label}</strong><small>${arm.actionCount} ${t("inspector.actions")} · ${t("inspector.period")} ${arm.period}</small></div><div class="timeline-track"><span style="width:${pct}%"></span></div><b>${pct}%</b></div>`;
    }).join("") || `<p class='hint'>${t("inspector.noArms")}</p>`;
  }

  function renderRelations(graph) {
    const edges = graph.edges || [];
    text("edge-count", `${edges.length} ${t("inspector.relationCount")}`);
    byId("relations").innerHTML = edges.slice(0, 80).map((edge) => `<span>${edge.source} → ${edge.target} · ${edge.type}</span>`).join("") || `<span>${t("inspector.noRelations")}</span>`;
  }

  function render(payload) {
    const { validation, puzzle, solution, graph, timeline, patterns } = payload;
    text("solution-title", solution.name || solution.source?.name || "Solution");
    text("puzzle-title", puzzle.name || solution.puzzleFile || "Puzzle");
    const validity = byId("validity");
    validity.textContent = validation.valid ? t("inspector.valid") : t("inspector.invalid");
    validity.className = `status-badge ${validation.valid ? "valid" : "invalid"}`;
    const validatorMetrics = validation.metrics || {};
    const declaredMetrics = solution.metrics || {};
    for (const key of ["cost", "cycles", "area", "instructions"]) text(`metric-${key}`, validatorMetrics[key] ?? declaredMetrics[key]);
    renderParts(solution);
    renderFacts(graph);
    renderArms(graph);
    renderPatterns(patterns);
    renderTimeline(timeline);
    renderRelations(graph);
    byId("raw-json").textContent = JSON.stringify(payload, null, 2);
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    results.hidden = true;
    status.textContent = t("inspector.running");
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
        fetch(`${API}/analyze/patterns`, { method: "POST", body: solutionForm() }),
        fetch(`${API}/parse/puzzle`, { method: "POST", body: puzzleForm }),
        fetch(`${API}/parse/solution`, { method: "POST", body: solutionForm() }),
      ]);
      if (responses.some((response) => !response.ok)) {
        const failed = responses.find((response) => !response.ok);
        throw new Error(`API ${failed.status}: ${await failed.text()}`);
      }
      const [validation, graph, timeline, patterns, puzzle, solution] = await Promise.all(responses.map((response) => response.json()));
      render({ validation, graph, timeline, patterns, puzzle, solution });
      status.textContent = t("inspector.complete");
    } catch (error) {
      console.error(error);
      status.textContent = `${t("inspector.failed")}: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  applyTranslations();
})();