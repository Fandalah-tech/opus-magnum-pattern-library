(() => {
  const API = "https://opus-validator-6gflgqb25q-nn.a.run.app";
  const ANALYZE_ENDPOINT = "/api/v1/analyze";
  const i18n = window.OpusI18n;
  const puzzleInput = document.querySelector("#puzzle-file");
  const solutionInput = document.querySelector("#solution-file");
  const button = document.querySelector("#analyze-button");
  const status = document.querySelector("#status");
  const results = document.querySelector("#results");
  const localeSelect = document.querySelector("#locale-select");
  const byId = (id) => document.getElementById(id);
  const text = (id, value) => { const node = byId(id); if (node) node.textContent = value ?? "—"; };
  const t = (key) => i18n.t(key);

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
    const s = graph.summary || {};
    const items = [[t("inspector.nodes"), s.nodeCount], [t("nav.relations"), s.edgeCount], [t("inspector.components"), s.componentCount], [t("inspector.arms"), s.armCount]];
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
      const p = arm.program || {};
      const histogram = Object.entries(p.instructionHistogram || {}).map(([name, count]) => `${name} ${count}`).join(" · ");
      const label = `${arm.partType}${arm.armNumber !== null && arm.armNumber !== undefined ? ` #${arm.armNumber}` : ""}`;
      return `<div class="arm"><strong><span>${label}</span><span>${p.instructionCount || 0}</span></strong><small>${histogram || t("inspector.noInstructions")}</small></div>`;
    }).join("") || `<p class='hint'>${t("inspector.noArms")}</p>`;
  }

  function renderPatterns(patterns) {
    const findings = patterns.findings || [];
    text("pattern-count", `${findings.length} ${t("inspector.patternCount")}`);
    byId("pattern-findings").innerHTML = findings.map((finding) => `<article class="pattern-finding"><div><strong>${t(`pattern.${finding.id}`)}</strong><small>${finding.id}</small></div><span class="confidence ${finding.confidence}">${t(`confidence.${finding.confidence}`)}</span><p>${finding.evidence?.length || 0} ${t("inspector.evidenceItems")}</p></article>`).join("") || `<p class='hint'>${t("inspector.noPatterns")}</p>`;
  }

  function renderDiagnostics(diagnostics) {
    const items = diagnostics.diagnostics || [];
    text("diagnostic-count", `${items.length} ${t("inspector.diagnosticCount")}`);
    byId("diagnostic-findings").innerHTML = items.map((item) => {
      const targets = item.targets?.length ? item.targets.join(", ") : "";
      return `<article class="pattern-finding"><div><strong>${t(`diagnostic.${item.id}`)}</strong><small>${item.id}${targets ? ` · ${targets}` : ""}</small></div><span class="confidence ${item.confidence}">${t(`severity.${item.severity}`)}</span><p>${item.evidence?.length || 0} ${t("inspector.evidenceItems")}</p></article>`;
    }).join("") || `<p class='hint'>${t("inspector.noDiagnostics")}</p>`;
  }

  function renderTimeline(timeline) {
    const s = timeline.summary || {};
    text("timeline-horizon", `${s.horizon ?? 0} ${t("inspector.cyclesAnalyzed")}`);
    const facts = [[t("inspector.activeCycles"), s.activeCycleCount], [t("inspector.globalIdle"), s.globalIdleCycles], [t("inspector.peakParallel"), s.peakParallelArms], [t("inspector.averageParallel"), s.averageParallelArms]];
    byId("timeline-facts").innerHTML = facts.map(([label, value]) => `<div><small>${label}</small><strong>${value ?? "—"}</strong></div>`).join("");
    byId("timeline-arms").innerHTML = (timeline.arms || []).map((arm) => {
      const pct = Math.max(0, Math.min(100, Math.round((arm.utilization || 0) * 100)));
      const label = `${arm.type}${arm.armNumber !== null && arm.armNumber !== undefined ? ` #${arm.armNumber}` : ""}`;
      return `<div class="timeline-row"><div class="timeline-label"><strong>${label}</strong><small>${arm.actionCount} ${t("inspector.actions")} · ${t("inspector.period")} ${arm.period}</small></div><div class="timeline-track"><span style="width:${pct}%"></span></div><b>${pct}%</b></div>`;
    }).join("") || `<p class='hint'>${t("inspector.noArms")}</p>`;
  }

  function renderRelations(graph) {
    const edges = graph.edges || [];
    text("edge-count", `${edges.length} ${t("inspector.relationCount")}`);
    byId("relations").innerHTML = edges.slice(0, 80).map((edge) => `<span>${edge.source} → ${edge.target} · ${edge.relation}</span>`).join("") || `<span>${t("inspector.noRelations")}</span>`;
  }

  function ensureValidatorPanel() {
    let panel = byId("validator-panel");
    if (panel) return panel;
    panel = document.createElement("article");
    panel.id = "validator-panel";
    panel.className = "panel full";
    panel.innerHTML = `<div class="panel-head"><h3>${t("validation.details")}</h3><span id="validator-name"></span></div><div id="validator-issues" class="arm-list"></div><details><summary>${t("validation.output")}</summary><pre id="validator-output"></pre></details>`;
    document.querySelector(".metrics").insertAdjacentElement("afterend", panel);
    return panel;
  }

  function renderValidation(validation) {
    const panel = ensureValidatorPanel();
    const issues = validation.issues || [];
    text("validator-name", `${validation.validator?.name || "omsim"} · ${validation.status || "unknown"}`);
    byId("validator-issues").innerHTML = issues.map((issue) => `<div class="arm"><strong>${issue.code || issue.severity || "Issue"}</strong><small>${issue.message || ""}</small></div>`).join("") || `<p class="hint">${t("validation.noIssues")}</p>`;
    text("validator-output", validation.rawOutput || t("validation.noOutput"));
    panel.hidden = validation.status === "valid" && !validation.rawOutput && issues.length === 0;
  }

  function render(payload) {
    const { validation, puzzle, solution, graph, timeline, patterns, diagnostics } = payload;
    text("solution-title", solution.name || solution.source?.name || "Solution");
    text("puzzle-title", puzzle.name || solution.puzzleFile || "Puzzle");

    const validationStatus = validation.status || (validation.valid === true ? "valid" : validation.valid === false ? "invalid" : "validator-error");
    const validity = byId("validity");
    validity.textContent = validationStatus === "valid" ? t("validation.valid") : validationStatus === "invalid" ? t("validation.invalid") : t("validation.error");
    validity.className = `status-badge ${validationStatus === "valid" ? "valid" : validationStatus === "invalid" ? "invalid" : "validator-error"}`;

    const vm = validation.metrics || {}, dm = solution.metrics || {};
    for (const key of ["cost", "cycles", "area", "instructions"]) text(`metric-${key}`, vm[key] ?? dm[key]);
    renderValidation(validation);
    renderParts(solution);
    renderFacts(graph);
    renderArms(graph);
    renderDiagnostics(diagnostics);
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
    const form = new FormData();
    form.append("puzzle", puzzleInput.files[0]);
    form.append("solution", solutionInput.files[0]);
    const endpoint = `${API}${ANALYZE_ENDPOINT}`;
    try {
      const response = await fetch(endpoint, { method: "POST", body: form });
      if (!response.ok) throw new Error(`POST ${ANALYZE_ENDPOINT} → ${response.status}: ${await response.text()}`);
      render(await response.json());
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