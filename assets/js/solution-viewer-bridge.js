(() => {
  const root = document.querySelector('#solution-viewer');
  if (!root || !window.OpusSolutionViewer) return;
  const viewer = window.OpusSolutionViewer.create(root);
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (response.ok && url.includes('/api/v1/analyze')) {
      response.clone().json().then((payload) => {
        if (payload?.solution) requestAnimationFrame(() => viewer.render(payload.solution, payload.graph));
      }).catch(() => {});
    }
    return response;
  };
  window.addEventListener('resize', () => viewer.fit());
})();
