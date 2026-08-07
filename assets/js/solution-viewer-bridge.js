(() => {
  const loadStylesheet = (href) => {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.append(link);
  };

  const loadScript = (src) => new Promise((resolve) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = resolve;
    document.head.append(script);
  });

  const init = () => {
    const root = document.querySelector('#solution-viewer');
    const runtime = window.OpusViewerRuntime;
    if (!root || !runtime) return;
    const viewer = runtime.mount(root);
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (response.ok && url.includes('/api/v1/analyze')) {
        response.clone().json().then((payload) => {
          if (!payload?.solution) return;
          requestAnimationFrame(() => runtime.renderPayload(payload, root));
        }).catch(() => {});
      }
      return response;
    };
    window.addEventListener('resize', () => viewer.fit());
  };

  loadStylesheet('assets/css/viewer-replay-enhancements.css');
  Promise.resolve()
    .then(() => loadScript('assets/js/opus-viewer-runtime.js'))
    .then(() => loadScript('assets/js/solution-viewer-symbols.js'))
    .then(() => loadScript('assets/js/output-product-preview.js'))
    .then(() => loadScript('assets/js/viewer-interactions.js'))
    .then(() => loadScript('assets/js/used-area-overlay.js'))
    .then(() => loadScript('assets/js/product-delivery-animation.js'))
    .then(() => loadScript('assets/js/viewer-polish.js'))
    .then(init);
})();
