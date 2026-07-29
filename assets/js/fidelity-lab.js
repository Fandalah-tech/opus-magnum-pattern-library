(() => {
  const atoms=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const source=()=>window.OpusAssetCalibrations?.source;
  const cropFor=metal=>window.OpusAssetCalibrations?.assets?.[`atom-${metal}`];
  const atomScene=metal=>({width:220,height:220,board:{cols:1,rows:1,size:38,offsetX:110,offsetY:110},atoms:[{element:metal,q:0,r:0}]});
  const model={outerDiameter:76,coreDiameter:48,rimWidth:8,rivetRadius:2.2,symbolScale:1};
  let mounting=false;

  function referenceStyle(crop){
    const normalizedZoom=Math.min(1400,Math.max(850,Number(crop.zoom||500)*1.8));
    return `background-image:url('${source()}');--lab-x:${crop.x}%;--lab-y:${crop.y}%;--lab-zoom:${normalizedZoom}%`;
  }

  function tile(label,body,className=''){
    return `<figure class="lab-tile ${className}"><div class="lab-frame">${body}</div><figcaption>${label}</figcaption></figure>`;
  }

  function renderLab(metal='Pb'){
    const crop=cropFor(metal);
    if(!crop||!window.OpusJS) return '';
    const reconstruction=window.OpusJS.render({...atomScene(metal),label:''});
    const reference=`<div class="lab-reference" style="${referenceStyle(crop)}"></div>`;
    const rendered=`<div class="lab-render">${reconstruction}</div>`;
    const difference=`<div class="lab-reference" style="${referenceStyle(crop)}"></div><div class="lab-render lab-difference">${reconstruction}</div>`;
    const heatmap='<div class="lab-heatmap" aria-label="Heatmap placeholder"></div>';
    return `<section class="fidelity-lab" data-metal="${metal}"><header><div><p class="eyebrow">FIDELITY LAB · PHASE 2</p><h3>Scientific atom reconstruction</h3><span>Four normalized square views using one shared coordinate frame.</span></div><label>Atom <select data-lab-metal>${atoms.map(x=>`<option${x===metal?' selected':''}>${x}</option>`).join('')}</select></label></header><div class="lab-grid">${tile('Reference',reference)}${tile('Reconstruction',rendered)}${tile('Difference',difference,'lab-composite')}${tile('Heatmap scaffold',heatmap)}</div><div class="lab-metrics"><strong>Parametric atom model v0.1</strong><dl><div><dt>Outer diameter</dt><dd>${model.outerDiameter}px</dd></div><div><dt>Core diameter</dt><dd>${model.coreDiameter}px</dd></div><div><dt>Rim width</dt><dd>${model.rimWidth}px</dd></div><div><dt>Rivet radius</dt><dd>${model.rivetRadius}px</dd></div><div><dt>Symbol scale</dt><dd>${model.symbolScale.toFixed(2)}</dd></div></dl><small>Reference and reconstruction now use the same fixed viewport. Pixel measurement remains the next stage.</small></div></section>`;
  }

  function mount(force=false){
    const gallery=document.querySelector('#asset-gallery');
    if(!gallery||gallery.hidden||mounting) return;
    mounting=true;
    try{
      let host=gallery.querySelector('.fidelity-lab-host');
      if(!host){
        host=document.createElement('div');
        host.className='fidelity-lab-host';
        host.dataset.metal='Pb';
        gallery.prepend(host);
      }
      const metal=host.dataset.metal||'Pb';
      if(!force&&host.dataset.renderedMetal===metal&&host.firstElementChild) return;
      host.innerHTML=renderLab(metal);
      host.dataset.renderedMetal=metal;
      host.querySelector('[data-lab-metal]')?.addEventListener('change',event=>{
        host.dataset.metal=event.target.value;
        host.dataset.renderedMetal='';
        mount(true);
      });
    }catch(error){
      console.error('Fidelity Lab mount failed',error);
    }finally{
      mounting=false;
    }
  }

  const gallery=document.querySelector('#asset-gallery');
  if(gallery){
    new MutationObserver(()=>mount()).observe(gallery,{childList:true});
    new MutationObserver(()=>mount()).observe(gallery,{attributes:true,attributeFilter:['hidden']});
  }
  window.OpusFidelityLab={mount};
  document.addEventListener('DOMContentLoaded',()=>mount());
})();