(() => {
  const iframe = document.querySelector('#solver-replay');
  const button = document.querySelector('#reload-replay');
  const status = document.querySelector('#lab-status');
  const REPORT = 'https://raw.githubusercontent.com/Fandalah-tech/opus-magnum-pattern-library/feature/disjoint-solver-readiness/reports/rotor-tail-best-candidate-replay.json';
  let resizeObserver = null;
  let mutationObserver = null;
  let resizeFrame = null;
  let selectedReplay = 'rotor-candidate-replay.html';

  const setStatus = (message, kind = '') => {
    status.textContent = message;
    status.className = kind;
  };

  const disconnect = () => {
    resizeObserver?.disconnect();
    mutationObserver?.disconnect();
    resizeObserver = null;
    mutationObserver = null;
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = null;
  };

  const resize = (doc = iframe.contentDocument) => {
    if (!doc) return;
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      resizeFrame = null;
      const height = Math.max(700, doc.documentElement?.scrollHeight || 0, doc.body?.scrollHeight || 0);
      iframe.style.height = `${Math.ceil(height + 6)}px`;
    });
  };

  const install = () => {
    const doc = iframe.contentDocument;
    if (!doc) throw new Error('Le replay intégré est inaccessible.');
    if (!doc.querySelector('#solver-lab-replay-style')) {
      const style = doc.createElement('style');
      style.id = 'solver-lab-replay-style';
      style.textContent = `
        html, body { height: auto !important; min-height: 0 !important; overflow: hidden !important; }
        body { background: #11100f !important; }
        main { width: min(1240px, calc(100% - 20px)) !important; padding: 18px 0 36px !important; }
        h1, main > p.warning { display: none !important; }
      `;
      doc.head.append(style);
    }
    disconnect();
    const observe = () => resize(doc);
    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(observe);
      resizeObserver.observe(doc.documentElement);
      if (doc.body) resizeObserver.observe(doc.body);
    }
    mutationObserver = new MutationObserver(observe);
    mutationObserver.observe(doc.documentElement, { subtree: true, childList: true, attributes: true });
    const replayStatus = doc.querySelector('#status, [data-rotor-status]');
    const text = replayStatus?.textContent?.trim() || '';
    const opus = selectedReplay === 'rotor-opus-replay.html';
    setStatus(text && !text.includes('Cannot read') ? text : `${opus ? 'Replay OpusJS' : 'Replay OMSIM'} chargé.`, 'good');
    resize(doc);
    window.setTimeout(() => resize(doc), 500);
  };

  const loadSelected = (cacheBust = Date.now()) => {
    disconnect();
    iframe.style.height = '760px';
    iframe.src = `${selectedReplay}?embedded=solver-lab&reload=${cacheBust}`;
  };

  const detectReplay = async () => {
    try {
      const response = await fetch(`${REPORT}?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) return false;
      const payload = await response.json();
      const ready = Boolean(payload?.renderContext?.solution && payload?.frames?.length);
      selectedReplay = ready ? 'rotor-opus-replay.html' : 'rotor-candidate-replay.html';
      const fullScreen = document.querySelector('.panel-head .secondary');
      if (fullScreen) fullScreen.href = selectedReplay;
      return ready;
    } catch {
      selectedReplay = 'rotor-candidate-replay.html';
      return false;
    }
  };

  const reload = async () => {
    button.disabled = true;
    button.textContent = 'Chargement…';
    setStatus('Vérification du dernier replay publié…');
    const opusReady = await detectReplay();
    setStatus(opusReady ? 'Contexte OpusJS détecté. Chargement du moteur graphique…' : 'Timeline complète encore indisponible; chargement du replay OMSIM actuel.');
    loadSelected();
  };

  iframe.addEventListener('load', () => {
    try {
      install();
    } catch (error) {
      console.error(error);
      setStatus(`Échec du replay : ${error.message}`, 'bad');
    } finally {
      button.disabled = false;
      button.textContent = 'Recharger le replay';
    }
  });
  button.addEventListener('click', reload);
  window.addEventListener('resize', () => resize());

  detectReplay().then((opusReady) => {
    const current = new URL(iframe.src, window.location.href).pathname.split('/').pop();
    if (opusReady && current !== selectedReplay) {
      setStatus('Contexte OpusJS détecté. Basculement automatique du replay…');
      loadSelected();
    }
  });
})();
