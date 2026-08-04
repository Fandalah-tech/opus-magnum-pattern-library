(() => {
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
            viewer.render(payload.solution, payload.graph);
            window.dispatchEvent(new CustomEvent('opus:analysisready', { detail: { payload, viewer } }));
          });
        }).catch(() => {});
      }
      return response;
    };
    window.addEventListener('resize', () => viewer.fit());
  };

  const enhancement = document.createElement('script');
  enhancement.src = 'assets/js/solution-viewer-symbols.js';
  enhancement.onload = init;
  enhancement.onerror = init;
  document.head.append(enhancement);
})();
