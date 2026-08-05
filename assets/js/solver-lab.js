(() => {
  const SAMPLE = {
    puzzle: 'samples/solver/P007.puzzle',
    puzzleName: 'P007.puzzle',
    solution: 'samples/solver/P007-auto.solution',
    solutionName: 'P007-auto.solution'
  };

  const iframe = document.querySelector('#solver-inspector');
  const button = document.querySelector('#load-demo');
  const status = document.querySelector('#lab-status');
  let loading = false;
  let resizeObserver = null;
  let mutationObserver = null;
  let resizeFrame = null;

  const setStatus = (message, kind = '') => {
    status.textContent = message;
    status.className = kind;
  };

  const waitFor = async (predicate, timeout = 30000, interval = 100) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      const value = predicate();
      if (value) return value;
      await new Promise((resolve) => window.setTimeout(resolve, interval));
    }
    throw new Error('Le visualisateur n’a pas répondu dans le délai prévu.');
  };

  const fetchBytes = async (url) => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${url} → ${response.status}`);
    return response.arrayBuffer();
  };

  const disconnectEmbeddedObservers = () => {
    resizeObserver?.disconnect();
    mutationObserver?.disconnect();
    resizeObserver = null;
    mutationObserver = null;
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = null;
  };

  const resizeEmbeddedView = (doc = iframe.contentDocument) => {
    if (!doc) return;
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      resizeFrame = null;
      const rootHeight = doc.documentElement?.scrollHeight || 0;
      const bodyHeight = doc.body?.scrollHeight || 0;
      const height = Math.max(720, rootHeight, bodyHeight);
      iframe.style.height = `${Math.ceil(height + 4)}px`;
    });
  };

  const observeEmbeddedView = (doc) => {
    disconnectEmbeddedObservers();
    const resize = () => resizeEmbeddedView(doc);
    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(resize);
      if (doc.documentElement) resizeObserver.observe(doc.documentElement);
      if (doc.body) resizeObserver.observe(doc.body);
    }
    mutationObserver = new MutationObserver(resize);
    mutationObserver.observe(doc.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['hidden', 'open']
    });
    resize();
  };

  const installEmbeddedView = (doc) => {
    if (!doc.querySelector('#solver-lab-embedded-style')) {
      const style = doc.createElement('style');
      style.id = 'solver-lab-embedded-style';
      style.textContent = `
        html, body { height: auto !important; min-height: 0 !important; overflow: hidden !important; }
        .topbar, .hero, .pair-library, .upload-panel, footer { display: none !important; }
        main { width: min(1180px, calc(100% - 24px)) !important; padding: 18px 0 54px !important; }
        #results { margin-top: 0 !important; }
        body { background: #11100f !important; }
      `;
      doc.head.append(style);
    }
    iframe.setAttribute('scrolling', 'no');
    observeEmbeddedView(doc);
  };

  const assignFile = (win, input, bytes, name) => {
    const file = new win.File([bytes], name, { type: 'application/octet-stream' });
    const transfer = new win.DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new win.Event('change', { bubbles: true }));
  };

  const initializeInspector = async () => {
    const win = iframe.contentWindow;
    const doc = iframe.contentDocument;
    if (!win || !doc) throw new Error('Impossible d’accéder à l’inspecteur intégré.');

    await waitFor(() => doc.querySelector('#puzzle-file') && doc.querySelector('#solution-file') && doc.querySelector('#analyze-button'));
    installEmbeddedView(doc);

    setStatus('Chargement du puzzle et de la solution générée…');
    const [puzzleBytes, solutionBytes] = await Promise.all([
      fetchBytes(SAMPLE.puzzle),
      fetchBytes(SAMPLE.solution)
    ]);

    const puzzleInput = doc.querySelector('#puzzle-file');
    const solutionInput = doc.querySelector('#solution-file');
    const analyze = doc.querySelector('#analyze-button');
    assignFile(win, puzzleInput, puzzleBytes, SAMPLE.puzzleName);
    assignFile(win, solutionInput, solutionBytes, SAMPLE.solutionName);

    await waitFor(() => !analyze.disabled);
    setStatus('Validation OMSim et construction du replay physique…');
    analyze.click();

    const results = await waitFor(() => {
      const node = doc.querySelector('#results');
      return node && !node.hidden ? node : null;
    }, 60000, 200);

    resizeEmbeddedView(doc);
    window.setTimeout(() => resizeEmbeddedView(doc), 250);
    window.setTimeout(() => resizeEmbeddedView(doc), 900);

    const badge = results.querySelector('#validity');
    const cycles = results.querySelector('#metric-cycles')?.textContent?.trim();
    const isValid = badge?.classList.contains('valid');
    if (!isValid) {
      const inspectorStatus = doc.querySelector('#status')?.textContent?.trim();
      throw new Error(inspectorStatus || 'La validation n’a pas retourné un résultat valide.');
    }

    setStatus(`Solution validée en ligne${cycles && cycles !== '—' ? ` · ${cycles} cycles` : ''}. Les contrôles de lecture sont prêts.`, 'good');
  };

  const load = async ({ refresh = false } = {}) => {
    if (loading) return;
    loading = true;
    button.disabled = true;
    button.textContent = 'Validation en cours…';
    setStatus('Initialisation du visualisateur…');
    try {
      if (refresh) {
        disconnectEmbeddedObservers();
        iframe.style.height = '720px';
        iframe.src = `inspector.html?embedded=solver-lab&reload=${Date.now()}`;
        await new Promise((resolve) => iframe.addEventListener('load', resolve, { once: true }));
      } else if (iframe.contentDocument?.readyState !== 'complete') {
        await new Promise((resolve) => iframe.addEventListener('load', resolve, { once: true }));
      }
      await initializeInspector();
    } catch (error) {
      console.error(error);
      setStatus(`Échec du chargement : ${error.message}`, 'bad');
    } finally {
      loading = false;
      button.disabled = false;
      button.textContent = 'Recharger et valider';
    }
  };

  button.addEventListener('click', () => load({ refresh: true }));
  window.addEventListener('resize', () => resizeEmbeddedView());
  window.addEventListener('DOMContentLoaded', () => load());
})();
