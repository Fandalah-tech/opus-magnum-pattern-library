(() => {
  const REPO = 'Fandalah-tech/opus-magnum-pattern-library';
  const BRANCH = 'feature/disjoint-solver-readiness';
  const WORKFLOW = 'om-local-worker.yml';
  const POLL_MS = 15000;

  const nodes = {
    badge: document.querySelector('#monitor-badge'),
    stage: document.querySelector('#monitor-stage'),
    elapsed: document.querySelector('#monitor-elapsed'),
    depth: document.querySelector('#monitor-depth'),
    visited: document.querySelector('#monitor-visited'),
    expanded: document.querySelector('#monitor-expanded'),
    score: document.querySelector('#monitor-score'),
    progress: document.querySelector('#monitor-progress-bar'),
    log: document.querySelector('#monitor-log'),
    updated: document.querySelector('#monitor-updated'),
    run: document.querySelector('#monitor-run')
  };

  if (!nodes.badge) return;

  const formatNumber = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('fr-CA') : '—';
  const formatDuration = (seconds) => {
    if (!Number.isFinite(seconds) || seconds < 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min ${String(s).padStart(2, '0')} s`;
  };

  const setBadge = (text, kind = '') => {
    nodes.badge.textContent = text;
    nodes.badge.className = `monitor-badge ${kind}`.trim();
  };

  const githubJson = async (url) => {
    const response = await fetch(url, {
      cache: 'no-store',
      headers: { Accept: 'application/vnd.github+json' }
    });
    if (!response.ok) throw new Error(`GitHub ${response.status}`);
    return response.json();
  };

  const rawJson = async (path) => {
    const url = `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${path}?t=${Date.now()}`;
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) return null;
    return response.json();
  };

  const campaignState = (live) => {
    const status = String(live?.status || '').toLowerCase();
    if (['running', 'in_progress', 'active'].includes(status)) return { label: 'En cours', kind: 'running' };
    if (['stopped', 'completed', 'success', 'finished'].includes(status)) {
      return live?.found
        ? { label: 'Solution trouvée', kind: 'success' }
        : { label: 'Terminée', kind: 'success' };
    }
    if (['failed', 'error'].includes(status)) return { label: 'Intervention', kind: 'failure' };
    return null;
  };

  const inferStage = (live) => {
    if (live?.status === 'stopped' || live?.status === 'completed') return 'Campagne terminée';
    if (live?.stage) return live.stage;
    return 'Inconnu';
  };

  const applyLive = (live) => {
    if (!live) return;
    nodes.stage.textContent = inferStage(live);
    nodes.elapsed.textContent = formatDuration(Number(live.elapsedSeconds ?? live.elapsed_seconds ?? live.timeLimitSeconds));
    nodes.depth.textContent = formatNumber(live.depth);
    nodes.visited.textContent = formatNumber(live.visitedStates ?? live.visited_states);
    nodes.expanded.textContent = formatNumber(live.expandedStates ?? live.expanded_states);
    nodes.score.textContent = formatNumber(live.bestScore ?? live.best_score);

    const maxDepth = Number(live.maxDepth ?? live.max_depth);
    const depth = Number(live.depth);
    const pct = Number.isFinite(maxDepth) && maxDepth > 0 && Number.isFinite(depth)
      ? Math.min(100, Math.max(0, (depth / maxDepth) * 100))
      : 0;
    nodes.progress.style.width = `${pct}%`;

    const state = campaignState(live);
    if (state) setBadge(state.label, state.kind);

    const lines = [
      live.message,
      Number.isFinite(depth) ? `Profondeur ${depth}${Number.isFinite(maxDepth) ? ` / ${maxDepth}` : ''}` : null,
      live.stoppedReason ? `Arrêt : ${live.stoppedReason}` : null,
      live.found === false ? 'Aucune solution complète trouvée.' : null
    ].filter(Boolean);
    if (lines.length) nodes.log.textContent = lines.join('\n');
  };

  const enrichWithWorker = async () => {
    try {
      const runsUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=${encodeURIComponent(BRANCH)}&per_page=1`;
      const runs = await githubJson(runsUrl);
      const run = runs.workflow_runs?.[0];
      if (!run) return;
      nodes.run.textContent = `Run #${run.run_number}`;
      nodes.run.href = run.html_url;
      const workerLabel = run.status === 'queued'
        ? 'Worker en file'
        : run.status === 'in_progress'
          ? 'Worker actif'
          : run.conclusion === 'success'
            ? 'Worker terminé'
            : `Worker : ${run.conclusion || run.status}`;
      nodes.updated.textContent = `${workerLabel} · actualisé ${new Date().toLocaleTimeString('fr-CA')}`;
    } catch {
      nodes.updated.textContent = `Campagne chargée · actualisé ${new Date().toLocaleTimeString('fr-CA')}`;
    }
  };

  const refresh = async () => {
    try {
      const live = await rawJson('reports/live-search-status.json');
      const summary = await rawJson('reports/rotor-autonomous-campaign.json');

      if (live) {
        applyLive(live);
      } else if (summary?.stages?.length) {
        const last = summary.stages.at(-1);
        nodes.stage.textContent = last.name || 'Campagne terminée';
        nodes.log.textContent = `${last.name} · code ${last.exitCode}\n${(last.stdout || '').slice(-900)}`.trim();
        setBadge(last.exitCode === 0 ? 'Terminée' : 'Intervention', last.exitCode === 0 ? 'success' : 'failure');
      } else {
        setBadge('Indisponible', 'failure');
        nodes.log.textContent = 'Aucun rapport de campagne publié.';
      }

      await enrichWithWorker();
    } catch (error) {
      setBadge('Indisponible', 'failure');
      nodes.log.textContent = `Impossible de lire l’état de la recherche : ${error.message}`;
      nodes.updated.textContent = `Nouvel essai dans ${POLL_MS / 1000} s`;
    }
  };

  refresh();
  window.setInterval(refresh, POLL_MS);
})();
