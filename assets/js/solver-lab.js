(() => {
  const iframe = document.querySelector('#solver-replay');
  const button = document.querySelector('#reload-replay');
  const status = document.querySelector('#lab-status');
  let resizeObserver = null;
  let mutationObserver = null;
  let resizeFrame = null;

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
      const height = Math.max(760, doc.documentElement?.scrollHeight || 0, doc.body?.scrollHeight || 0);
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
    const replayStatus = doc.querySelector('#status');
    const text = replayStatus?.textContent?.trim() || '';
    setStatus(text && !text.includes('Cannot read') ? text : 'Replay chargé. Les contrôles de lecture sont prêts.', 'good');
    resize(doc);
    window.setTimeout(() => resize(doc), 500);
  };

  const reload = () => {
    button.disabled = true;
    button.textContent = 'Chargement…';
    setStatus('Régénération de la vue intégrée…');
    disconnect();
    iframe.style.height = '760px';
    iframe.src = `rotor-candidate-replay.html?embedded=solver-lab&reload=${Date.now()}`;
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
})();
