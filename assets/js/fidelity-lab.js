(() => {
  const atoms=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const source=()=>window.OpusAssetCalibrations?.source;
  const cropFor=metal=>window.OpusAssetCalibrations?.assets?.[`atom-${metal}`];
  const atomScene=metal=>({width:220,height:220,board:{cols:1,rows:1,size:38,offsetX:110,offsetY:110},atoms:[{element:metal,q:0,r:0}]});
  const model={outerDiameter:76,coreDiameter:48,rimWidth:8,rivetRadius:2.2,symbolScale:1};
  let mounting=false;

  function referenceStyle(crop){
    return `background-image:url('${source()}');--lab-x:${crop.x}%;--lab-y:${crop.y}%;--lab-zoom:${crop.zoom}%`;
  }

  function renderLab(metal='Pb'){
    const crop=cropFor(metal);
    if(!crop||!window.OpusJS) return '';
    const reconstruction=window.OpusJS.render({...atomScene(metal),label:''});
    return `<section class="fidelity-lab" data-metal="${metal}"><header><div><p class="eyebrow">FIDELITY LAB · PHASE 2</p><h3>Scientific atom reconstruction</h3><span>Normalized four-view comparison using the shared crop registry.</span></div><label>Atom <select data-lab-metal>${atoms.map(x=>`<option${x===metal?' selected':''}>${x}</option>`).join('')}</select></label></header><div class="lab-grid"><figure><div class="lab-reference" style="${referenceStyle(crop)}"></div><figcaption>Reference</figcaption></figure><figure><div class="lab-render">${reconstruction}</div><figcaption>Reconstruction</figcaption></figure><figure><div class="lab-reference" style="${referenceStyle(crop)}"></div><div class="lab-render lab-difference">${reconstruction}</div><figcaption>Difference</figcaption></figure><figure><div class="lab-heatmap"><span></span></div><figcaption>Heatmap scaffold</figcaption></figure></div><div class="lab-metrics"><strong>Parametric atom model v0.1</strong><dl><div><dt>Outer diameter</dt><dd>${model.outerDiameter}px</dd></div><div><dt>Core diameter</dt><dd>${model.coreDiameter}px</dd></div><div><dt>Rim width</dt><dd>${model.rimWidth}px</dd></div><div><dt>Rivet radius</dt><dd>${model.rivetRadius}px</dd></div><div><dt>Symbol scale</dt><dd>${model.symbolScale.toFixed(2)}</dd></div></dl><small>Values currently describe the reconstruction model. Automated reference measurements and numerical error scores are the next stage.</small></div></section>`;
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
