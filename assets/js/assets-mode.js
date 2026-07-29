(() => {
  // Assets routing is handled by the primary application router in app.js.
  // This compatibility shim only asks the optional Fidelity Lab to mount
  // after an Assets render; it never renders the gallery itself.
  const tab=document.querySelector('[data-mode="assets"]');
  const search=document.querySelector('#search-input');
  const reset=document.querySelector('#reset-filters');
  const mount=()=>queueMicrotask(()=>window.OpusFidelityLab?.mount());
  tab?.addEventListener('click',mount);
  search?.addEventListener('input',()=>{if(tab?.classList.contains('active'))mount();});
  reset?.addEventListener('click',()=>{if(tab?.classList.contains('active'))mount();});
})();
