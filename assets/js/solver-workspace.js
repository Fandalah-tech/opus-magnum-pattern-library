(() => {
  const repo = 'Fandalah-tech/opus-magnum-pattern-library';
  const branch = 'feature/disjoint-solver-readiness';
  const replayUrl = `https://raw.githubusercontent.com/${repo}/${branch}/reports/rotor-tail-best-candidate-replay.json`;
  const liveUrl = `https://raw.githubusercontent.com/${repo}/${branch}/reports/rotor-a41-cycle-live.json`;
  const root = document.querySelector('#solution-viewer');
  const status = document.querySelector('#solver-status');
  const loading = document.querySelector('#solver-loading');
  const viewerWrap = document.querySelector('.viewer-wrap');
  const jumpSolver = document.querySelector('#jump-solver');
  const refresh = document.querySelector('#refresh-solver');
  const $ = id => document.getElementById(id);
  let research = null;
  let solverStartIndex = 0;

  if (!root || !window.OpusViewerRuntime || !window.OpusScene) {
    if (status) status.textContent = 'Le moteur graphique canonique n’est pas disponible.';
    return;
  }

  const atomKey = position => `${Number(position?.[0] || 0)},${Number(position?.[1] || 0)}`;
  const normalizeElement = value => value === 'W' ? 'water' : value === 'S' ? 'salt' : String(value || 'salt').toLowerCase();

  function connectedMolecules(state = {}) {
    const atoms = (state.atoms || []).map((atom, index) => ({
      id: String(atom.id ?? `atom-${index}`),
      element: normalizeElement(atom.element),
      position: [...(atom.position || [0, 0])]
    }));
    const byPosition = new Map(atoms.map(atom => [atomKey(atom.position), atom]));
    const adjacency = new Map(atoms.map(atom => [atom.id, new Set()]));
    const bonds = (state.bonds || []).map((bond, index) => {
      const from = bond.from || bond.aPosition || bond.a || [0, 0];
      const to = bond.to || bond.bPosition || bond.b || [0, 0];
      const a = byPosition.get(atomKey(from));
      const b = byPosition.get(atomKey(to));
      if (a && b) {
        adjacency.get(a.id)?.add(b.id);
        adjacency.get(b.id)?.add(a.id);
      }
      return {
        id: String(bond.id ?? `bond-${index}`),
        from: [...from],
        to: [...to],
        type: bond.type || 'normal',
        atomA: a?.id,
        atomB: b?.id
      };
    });
    const seen = new Set();
    const molecules = [];
    for (const atom of atoms) {
      if (seen.has(atom.id)) continue;
      const queue = [atom.id];
      const component = new Set();
      while (queue.length) {
        const id = queue.pop();
        if (seen.has(id)) continue;
        seen.add(id);
        component.add(id);
        for (const next of adjacency.get(id) || []) if (!seen.has(next)) queue.push(next);
      }
      molecules.push({
        id: `molecule-${molecules.length + 1}`,
        atoms: atoms.filter(item => component.has(item.id)),
        bonds: bonds.filter(bond => component.has(bond.atomA) && component.has(bond.atomB)),
        heldBy: []
      });
    }
    return molecules;
  }

  function armStates(state = {}) {
    return Object.entries(state.arms || {}).map(([partId, arm]) => ({
      partId: String(arm.partId ?? partId),
      origin: [...(arm.origin || [0, 0])],
      tips: (arm.tips || []).map((tip, branchIndex) => ({
        branchIndex: Number(tip.branchIndex ?? branchIndex),
        position: [...(tip.position || arm.origin || [0, 0])]
      })),
      rotation: Number(arm.rotation ?? 0),
      length: Number(arm.length ?? arm.baseLength ?? 1),
      baseLength: Number(arm.baseLength ?? arm.length ?? 1),
      grabbing: Boolean(arm.grabbing),
      heldMoleculeIds: [...(arm.heldMoleculeIds || [])]
    }));
  }

  function eventFromAction(frame) {
    const action = frame?.action;
    if (!action || typeof action !== 'object') return [];
    const partId = action.partId ?? action.armId ?? action.part_id ?? null;
    const instruction = action.instruction ?? action.action ?? action.kind ?? null;
    return partId && instruction ? [{ partId: String(partId), instruction: String(instruction) }] : [];
  }

  function frameForScene(frame, index) {
    const state = frame?.state || {};
    return {
      phaseLabel: index === 0 ? 'initial' : null,
      cycle: Number(state.cycle ?? Math.max(-1, index - 1)),
      displayCycle: Number(state.cycle ?? Math.max(0, index)),
      events: eventFromAction(frame),
      armStates: armStates(state),
      molecules: connectedMolecules(state)
    };
  }

  function payloadFromResearch(data) {
    const frames = (data.frames || []).map(frameForScene);
    const context = data.renderContext || {};
    return {
      validation: {
        status: data.isCompleteSolution ? 'valid' : 'research-candidate',
        metrics: context.solution?.metrics || {}
      },
      puzzle: context.puzzle,
      solution: context.solution,
      graph: { nodes: [], edges: [], summary: {} },
      diagnostics: { summary: {}, diagnostics: [] },
      patterns: { summary: {}, findings: [] },
      replay: {
        summary: { cycleCount: Math.max(0, frames.length - 1) },
        capabilities: { physicalArmAnimation: true, moleculeAnimation: true, multiBranchGrab: true },
        frames
      }
    };
  }

  async function fetchJson(url, optional = false) {
    const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
    if (optional && response.status === 404) return null;
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function badgeClass(value) {
    const text = String(value || '').toLowerCase();
    if (/running|working|search|valid|complete/.test(text)) return 'badge good';
    if (/fail|error|offline|stopped/.test(text)) return 'badge bad';
    return 'badge warn';
  }

  function renderTelemetry(data, live) {
    research = data;
    solverStartIndex = Math.max(0, Number(data.solverStartIndex || 0));
    $('solver-candidate').textContent = data.title || 'Candidat Rotor';
    $('solver-score').textContent = Number.isFinite(Number(data.bestScore)) ? Number(data.bestScore).toLocaleString('fr-CA') : '—';
    $('solver-frames').textContent = Number(data.frames?.length || 0).toLocaleString('fr-CA');
    $('solver-relay').textContent = data.frames?.[solverStartIndex]?.state?.cycle ?? '—';
    $('solver-actions').textContent = Number(data.solverActionCount || 0).toLocaleString('fr-CA');
    const badge = $('solver-live-badge');
    const stage = live?.stage || live?.status || (data.isCompleteSolution ? 'complete' : 'research-candidate');
    badge.textContent = stage;
    badge.className = badgeClass(stage);
    $('solver-stage').textContent = stage;
    $('solver-visited').textContent = Number(live?.visited ?? live?.statesVisited ?? 0).toLocaleString('fr-CA');
    $('solver-depth').textContent = live?.depth ?? '—';
    $('solver-frontier').textContent = live?.frontier ?? '—';
    $('solver-log').textContent = live?.message || live?.reason || `Candidat ${data.bestScore ?? '—'} · ${data.frames?.length || 0} frames · relais solver à l’image ${solverStartIndex + 1}.`;
    $('solver-source').textContent = branch;
  }

  function revealViewer() {
    viewerWrap?.classList.remove('loading');
    if (loading) loading.hidden = true;
  }

  function jumpToSolver() {
    const range = root.querySelector('[data-replay-range]');
    if (!range) return;
    range.value = String(Math.max(0, Math.min(Number(range.max || 0), solverStartIndex)));
    range.dispatchEvent(new Event('input', { bubbles: true }));
  }

  async function load() {
    status.textContent = 'Lecture du rapport A41 et construction de la Scene…';
    status.classList.remove('error');
    viewerWrap?.classList.add('loading');
    if (loading) {
      loading.hidden = false;
      loading.textContent = 'Construction de la Scene A41…';
    }
    try {
      const [data, live] = await Promise.all([fetchJson(replayUrl), fetchJson(liveUrl, true)]);
      if (!data?.renderContext?.solution || !data?.renderContext?.puzzle) throw new Error('Le rapport ne contient pas de contexte graphique complet.');
      renderTelemetry(data, live);
      const payload = payloadFromResearch(data);
      window.OpusViewerRuntime.renderPayload(payload, root);
      await new Promise(resolve => requestAnimationFrame(resolve));
      window.OpusViewerRuntime.fit(root);
      revealViewer();
      status.textContent = `Scene canonique chargée · ${data.frames?.length || 0} frames · source ${branch}.`;
      document.body.dataset.solverSceneReady = 'true';
      window.__OPUS_SOLVER_RESEARCH__ = data;
      window.__OPUS_SOLVER_LIVE__ = live;
    } catch (error) {
      console.error(error);
      status.textContent = `Chargement impossible : ${error.message}`;
      status.classList.add('error');
      if (loading) loading.textContent = 'Replay A41 indisponible pour le moment.';
    }
  }

  jumpSolver?.addEventListener('click', jumpToSolver);
  refresh?.addEventListener('click', load);
  root.addEventListener('opus:replayframe', event => {
    const frame = event.detail?.scene?.timeline?.frame;
    const index = Number(event.detail?.scene?.timeline?.frameIndex ?? 0);
    const meta = research?.frames?.[index];
    if ($('solver-frame')) $('solver-frame').textContent = `${index + 1} / ${research?.frames?.length || 0}`;
    if ($('solver-cycle')) $('solver-cycle').textContent = frame?.cycle ?? '—';
    if ($('solver-segment')) $('solver-segment').textContent = index >= solverStartIndex ? 'Solver' : 'Préfixe humain';
    if ($('solver-frame-score')) $('solver-frame-score').textContent = meta?.state?.score ?? '—';
  });

  load();
})();