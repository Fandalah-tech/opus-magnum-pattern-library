(() => {
  const DATA = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/feature/disjoint-solver-readiness/reports/rotor-tail-best-candidate-replay.json';
  const root = document.querySelector('#solution-viewer');
  const slider = document.querySelector('[data-rotor-range]');
  const position = document.querySelector('[data-rotor-position]');
  const cycleNode = document.querySelector('[data-rotor-cycle]');
  const scoreNode = document.querySelector('[data-rotor-score]');
  const stepNode = document.querySelector('[data-rotor-step]');
  const segmentNode = document.querySelector('[data-rotor-segment]');
  const actionNode = document.querySelector('[data-rotor-action]');
  const statusNode = document.querySelector('[data-rotor-status]');
  const mode = document.querySelector('[data-rotor-mode]');
  const play = document.querySelector('[data-rotor-play]');
  let data = null;
  let viewer = null;
  let index = 0;
  let timer = null;

  const atomKey = (position) => `${position?.[0] ?? 0},${position?.[1] ?? 0}`;
  const normalizeElement = (value) => value === 'W' ? 'water' : value === 'S' ? 'salt' : String(value || 'salt').toLowerCase();

  function connectedMolecules(state) {
    const atoms = (state.atoms || []).map((atom, atomIndex) => ({
      id: String(atom.id ?? `atom-${atomIndex}`),
      element: normalizeElement(atom.element),
      position: [...(atom.position || [0, 0])]
    }));
    const byPosition = new Map(atoms.map((atom) => [atomKey(atom.position), atom]));
    const adjacency = new Map(atoms.map((atom) => [atom.id, new Set()]));
    const bonds = (state.bonds || []).map((bond, bondIndex) => {
      const from = bond.from || bond.aPosition || bond.a || [0, 0];
      const to = bond.to || bond.bPosition || bond.b || [0, 0];
      const a = byPosition.get(atomKey(from));
      const b = byPosition.get(atomKey(to));
      if (a && b) { adjacency.get(a.id)?.add(b.id); adjacency.get(b.id)?.add(a.id); }
      return { id: String(bond.id ?? `bond-${bondIndex}`), from: [...from], to: [...to], type: bond.type || 'normal', atomA: a?.id, atomB: b?.id };
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
        seen.add(id); component.add(id);
        for (const next of adjacency.get(id) || []) if (!seen.has(next)) queue.push(next);
      }
      const moleculeAtoms = atoms.filter((item) => component.has(item.id));
      const moleculeBonds = bonds.filter((bond) => component.has(bond.atomA) && component.has(bond.atomB));
      molecules.push({ id: `molecule-${molecules.length + 1}`, atoms: moleculeAtoms, bonds: moleculeBonds, heldBy: [] });
    }
    return molecules;
  }

  function armStates(state) {
    return Object.entries(state.arms || {}).map(([partId, arm]) => ({
      partId: String(arm.partId ?? partId),
      origin: [...(arm.origin || [0, 0])],
      tips: (arm.tips || []).map((tip, branchIndex) => ({ branchIndex: tip.branchIndex ?? branchIndex, position: [...(tip.position || arm.origin || [0, 0])] })),
      rotation: arm.rotation ?? 0,
      length: arm.length ?? arm.baseLength ?? 1,
      baseLength: arm.baseLength ?? arm.length ?? 1,
      grabbing: Boolean(arm.grabbing),
      heldMoleculeIds: arm.heldMoleculeIds || []
    }));
  }

  function frameForViewer(frame) {
    return { cycle: frame.state?.cycle, molecules: connectedMolecules(frame.state || {}), armStates: armStates(frame.state || {}) };
  }

  function bounds() {
    return mode?.value === 'solver' ? [data.solverStartIndex, data.solverEndIndex] : [0, data.frames.length - 1];
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    if (play) play.textContent = 'Lecture';
  }

  function show(nextIndex, duration = 140) {
    if (!data) return;
    const [min, max] = bounds();
    index = Math.max(min, Math.min(max, nextIndex));
    const frame = data.frames[index];
    const solver = frame.segment === 'solver' || index >= data.solverStartIndex;
    root.dispatchEvent(new CustomEvent('opus:replayframe', { bubbles: true, detail: { frame: frameForViewer(frame), animationDuration: duration } }));
    slider.value = index;
    position.textContent = `Image ${index + 1} / ${data.frames.length}`;
    cycleNode.textContent = frame.state?.cycle ?? '—';
    scoreNode.textContent = frame.state?.score ?? '—';
    stepNode.textContent = solver ? `${Math.max(0, index - data.solverStartIndex)}/${data.solverActionCount}` : `${index}/${data.solverStartIndex}`;
    segmentNode.textContent = solver ? 'Segment solver' : 'Préfixe humain';
    segmentNode.className = `segment-badge${solver ? ' solver' : ''}`;
    actionNode.textContent = index === 0 ? 'État initial' : index === data.solverStartIndex ? 'Prise en charge par le solver' : JSON.stringify(frame.action || {}, null, 2);
  }

  function bind() {
    document.querySelector('[data-rotor-start]')?.addEventListener('click', () => { stop(); mode.value = 'all'; show(0, 0); });
    document.querySelector('[data-rotor-solver-start]')?.addEventListener('click', () => { stop(); mode.value = 'solver'; show(data.solverStartIndex, 0); });
    document.querySelector('[data-rotor-prev]')?.addEventListener('click', () => show(index - 1));
    document.querySelector('[data-rotor-next]')?.addEventListener('click', () => show(index + 1));
    slider?.addEventListener('input', () => { stop(); show(Number(slider.value), 0); });
    mode?.addEventListener('change', () => { stop(); const [min, max] = bounds(); if (index < min || index > max) show(min, 0); });
    play?.addEventListener('click', () => {
      if (timer) return stop();
      const [min, max] = bounds();
      if (index >= max) show(min, 0);
      play.textContent = 'Pause';
      timer = setInterval(() => { const [, end] = bounds(); if (index >= end) stop(); else show(index + 1, 240); }, 520);
    });
  }

  fetch(`${DATA}?t=${Date.now()}`, { cache: 'no-store' })
    .then((response) => { if (!response.ok) throw new Error(`Replay indisponible (${response.status})`); return response.json(); })
    .then((payload) => {
      data = payload;
      if (!data.renderContext?.solution || !window.OpusSolutionViewer) throw new Error('Le contexte OpusJS n’est pas encore publié par le runner.');
      viewer = window.OpusSolutionViewer.create(root);
      viewer.render(data.renderContext.solution, null, data.renderContext.puzzle, null);
      window.dispatchEvent(new CustomEvent('opus:analysisready'));
      slider.max = data.frames.length - 1;
      statusNode.textContent = `${data.frames.length} images · rendu OpusJS · relais au cycle ${data.frames[data.solverStartIndex]?.state?.cycle ?? '—'}.`;
      bind();
      show(0, 0);
    })
    .catch((error) => {
      statusNode.textContent = `${error.message} Le visualiseur basculera automatiquement sur OpusJS après la prochaine génération complète.`;
      statusNode.classList.add('warning');
    });
})();
