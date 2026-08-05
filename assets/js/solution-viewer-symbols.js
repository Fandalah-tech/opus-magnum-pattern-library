(() => {
  const base = window.OpusSolutionViewer;
  if (!base) return;

  // Symbols are now rendered natively by solution-viewer.js so every piece
  // participates in the same typed layers, selection overlay, and inspector.
  // Keep this compatibility wrapper because older pages still load the file
  // dynamically through solution-viewer-bridge.js.
  window.OpusSolutionViewer = {
    ...base,
    create(root) {
      const viewer = base.create(root);
      root.classList.add("viewer-symbols-ready");
      return viewer;
    }
  };
})();