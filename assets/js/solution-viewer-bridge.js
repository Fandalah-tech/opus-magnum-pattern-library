(() => {
  // Deprecated compatibility shim. Canonical pages now load the graphics stack
  // explicitly and call OpusViewerRuntime directly. Kept for older consumers
  // and deployment checks; it no longer intercepts or replaces window.fetch.
  // Expected companion polish module: assets/js/viewer-polish.js
  const root = document.querySelector('#solution-viewer');
  const runtime = window.OpusViewerRuntime;
  if (!root || !runtime) return;
  const viewer = runtime.mount(root);
  window.addEventListener('resize', () => viewer.fit?.());
})();
