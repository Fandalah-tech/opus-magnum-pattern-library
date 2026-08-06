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

  const inferStage = (run, live) => {
    if (live?.stage) return live.stage;
    if (run.status === 'queued') return 'En file';
    if (run.status === 'in_progress') return 'Opération OMSIM en cours';
    if (run.conclusion === 'success') return 'Campagne terminée';
    if (run.conclusion) return `Arrêtée · ${run.conclusion}`;
    return 'Inconnu';
  };

  const applyLive = (live) => {
    if (!live) return;
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
    const lines = [
      live.message,
      Number.isFinite(depth) ? `Profondeur ${depth}${Number.isFinite(maxDepth) ? ` / ${maxDepth}` : ''}` : null,
      live.stoppedReason ? `Arrêt : ${live.stoppedReason}` : null
    ].filter(Boolean);
    if (lines.length) nodes.log.textContent = lines.join('\n');
  };

  const refresh = async () => {
    try {
      const runsUrl = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=${encodeURIComponent(BRANCH)}&per_page=1`;
      const runs = await githubJson(runsUrl);
      const run = runs.workflow_runs?.[0];
      if (!run) throw new Error('Aucune campagne trouvée');

      const live = await rawJson('reports/live-search-status.json');
      const summary = await rawJson('reports/rotor-autonomous-campaign.json');
      const started = new Date(run.run_started_at || run.created_at).getTime();
      const ended = run.updated_at ? new Date(run.updated_at).getTime() : Date.now();
      const elapsed = Math.max(0, ((run.status === 'completed' ? ended : Date.now()) - started) / 1000);

      nodes.stage.textContent = inferStage(run, live);
      nodes.elapsed.textContent = formatDuration(elapsed);
      nodes.run.textContent = `Run #${run.run_number}`;
      nodes.run.href = run.html_url;
      nodes.updated.textContent = `Actualisé ${new Date().toLocaleTimeString('fr-CA')}`;

      if (run.status === 'in_progress' || run.status === 'queued') setBadge('En cours', 'running');
      else if (run.conclusion === 'success') setBadge('Terminé', 'success');
      else setBadge('Intervention', 'failure');

      if (live) {
        applyLive(live);
      } else if (summary?.stages?.length) {
        const last = summary.stages.at(-1);
        nodes.log.textContent = `${last.name} · code ${last.exitCode}\n${(last.stdout || '').slice(-900)}`.trim();
      } else {
        nodes.log.textContent = run.status === 'in_progress'
          ? 'La campagne travaille sur le runner. Les métriques détaillées apparaîtront à partir des campagnes instrumentées avec heartbeat.'
          : `Dernière conclusion GitHub : ${run.conclusion || run.status}.`;
      }
    } catch (error) {
      setBadge('Indisponible', 'failure');
      nodes.log.textContent = `Impossible de lire l’état de la recherche : ${error.message}`;
      nodes.updated.textContent = `Nouvel essai dans ${POLL_MS / 1000} s`;
    }
  };

  refresh();
  window.setInterval(refresh, POLL_MS);
})();
