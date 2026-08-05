(() => {
  const loadScript = (src) => new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = resolve;
    document.head.append(script);
  });

  const init = () => {
    const root = document.querySelector('#solution-viewer');
    if (!root || !window.OpusSolutionViewer) return;
    const viewer = window.OpusSolutionViewer.create(root);
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (response.ok && url.includes('/api/v1/analyze')) {
        response.clone().json().then((payload) => {
          if (!payload?.solution) return;
          requestAnimationFrame(() => {
            viewer.render(payload.solution, payload.graph, payload.puzzle, payload.replay);
            window.dispatchEvent(new CustomEvent('opus:analysisready', { detail: { payload, viewer } }));
          });
        }).catch(() => {});
      }
      return response;
    };
    window.addEventListener('resize', () => viewer.fit());
  };

  Promise.resolve()
    .then(() => loadScript('assets/js/solution-viewer-symbols.js'))
    .then(() => loadScript('assets/js/output-product-preview.js'))
    .then(init);
})();
