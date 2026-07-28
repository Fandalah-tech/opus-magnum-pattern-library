(() => {
  const tab=document.querySelector('[data-mode="assets"]');
  const gallery=document.querySelector('#asset-gallery');
  const grid=document.querySelector('#pattern-grid');
  const concepts=document.querySelector('#concept-grid');
  const graph=document.querySelector('#graph-view');
  const empty=document.querySelector('#empty-state');
  const title=document.querySelector('#view-title');
  const kicker=document.querySelector('#view-kicker');
  const search=document.querySelector('#search-input');
  const sidebar=document.querySelector('.sidebar');
  if(!tab||!gallery||!window.OpusAssetGallery)return;
  const activate=()=>{
    document.querySelectorAll('.mode-tab').forEach(x=>x.classList.toggle('active',x===tab));
    grid.hidden=true;concepts.hidden=true;graph.hidden=true;gallery.hidden=false;empty.hidden=true;
    sidebar.classList.add('filters-disabled');
    title.textContent='Canonical asset validation';
    kicker.textContent='TEMPORARY REVIEW GALLERY';
    const count=window.OpusAssetGallery.render(gallery,search.value);
    empty.hidden=count>0;
  };
  tab.addEventListener('click',()=>setTimeout(activate,0));
  search.addEventListener('input',()=>{if(tab.classList.contains('active'))setTimeout(activate,0)});
  document.querySelector('#reset-filters')?.addEventListener('click',()=>{if(tab.classList.contains('active'))setTimeout(activate,0)});
})();