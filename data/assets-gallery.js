(() => {
  const board={cols:5,rows:3,size:38,offsetX:62,offsetY:58};
  const references={
    atoms:{title:'Atom layout — production reference',image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/48f7201e-226e-4949-a318-348c4ca2d34c/atom_layout_B_1200.png',page:'https://www.kylesteed.net/opus-magnum',credit:'Kyle Steed · Opus Magnum production art'},
    parts:{title:'Parts layout — production reference',image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/63013d2b-70b4-4d59-88bb-56a94203e11a/parts_layout_withFrame_1200.png',page:'https://www.kylesteed.net/opus-magnum',credit:'Kyle Steed · Opus Magnum production art'}
  };
  const atomTypes=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const atomNotes=['Layered rim, recessed core and material highlight added in v0.2','Use the crop calibrator to isolate the matching production atom','Confirm alchemical symbol weight, scale and material-specific hue'];
  const entries=[
    ...atomTypes.map(element=>({id:`atom-${element}`,group:'Atoms',name:element,status:'draft',reference:'atoms',calibratable:true,notes:atomNotes,scene:{width:420,height:250,board,atoms:[{element,q:2,r:1}]}})),
    {id:'arm-1',group:'Mechanisms',name:'Arm — length 1',status:'draft',reference:'parts',calibratable:false,notes:['Pivot assembly needs canonical layered construction','Arm body and grabber geometry are placeholders','Metal shading is too flat'],scene:{width:420,height:250,board,arms:[{q:1,r:1,length:1,rotation:0}]}},
    {id:'arm-2',group:'Mechanisms',name:'Arm — length 2',status:'draft',reference:'parts',calibratable:false,notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:2,rotation:0}]}},
    {id:'arm-3',group:'Mechanisms',name:'Arm — length 3',status:'draft',reference:'parts',calibratable:false,notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:3,rotation:0}]}},
    {id:'glyph-projection',group:'Glyphs',name:'Glyph of Projection',status:'draft',reference:'parts',calibratable:false,notes:['Current radial form is not canonical','Internal material and rune geometry must be rebuilt'],scene:{width:420,height:250,board,glyphs:[{type:'projection',q:2,r:1}]}},
    {id:'glyph-bonding',group:'Glyphs',name:'Glyph of Bonding',status:'draft',reference:'parts',calibratable:false,notes:['Current symbol is only a semantic placeholder','Canonical plate and bonding marks are missing'],scene:{width:420,height:250,board,glyphs:[{type:'bonding',q:2,r:1}]}},
    {id:'track-straight',group:'Tracks',name:'Straight Track',status:'draft',reference:'parts',calibratable:false,notes:['Rail construction and nodes need canonical geometry','Current dashed line is not visually faithful'],scene:{width:420,height:250,board,tracks:[{q1:0,r1:1,q2:3,r2:1}]}},
    {id:'board',group:'Board',name:'Hexagonal board background',status:'draft',reference:'parts',calibratable:false,notes:['Hex borders are too prominent','Surface lacks material depth and vignette'],scene:{width:420,height:250,board}}
  ];
  const key=id=>`opusjs-fidelity-${id}`;
  const local=id=>{try{return JSON.parse(localStorage.getItem(key(id))||'null')}catch{return null}};
  const shared=id=>window.OpusAssetCalibrations?.assets?.[id]||null;
  const saved=id=>local(id)||shared(id);
  const sourceOf=id=>local(id)?'local':shared(id)?'shared':null;
  const atomEntries=()=>entries.filter(x=>x.calibratable);
  const calibrations=()=>Object.fromEntries(atomEntries().map(x=>[x.id,saved(x.id)]).filter(([,v])=>v));
  const validCrop=v=>v&&Number.isFinite(v.x)&&Number.isFinite(v.y)&&Number.isFinite(v.zoom)&&v.x>=0&&v.x<=100&&v.y>=0&&v.y<=100&&v.zoom>=100&&v.zoom<=700;
  function referenceCard(ref){const section=document.createElement('article');section.className='reference-sheet';section.innerHTML=`<a href="${ref.page}" target="_blank" rel="noopener noreferrer"><img src="${ref.image}" alt="${ref.title}" loading="lazy"></a><div><p class="eyebrow">CONTEXT REFERENCE</p><h3>${ref.title}</h3><small>${ref.credit}. Context only; asset crops are calibrated separately.</small></div>`;return section;}
  function preview(item){
    const ref=references[item.reference],crop=saved(item.id),active=Boolean(crop),origin=sourceOf(item.id),render=window.OpusJS.render({...item.scene,label:item.name});
    const x=crop?.x??50,y=crop?.y??50,z=crop?.zoom??100;
    const source=item.calibratable?`<div class="fidelity-reference" style="background-image:url('${ref.image}');--crop-x:${x}%;--crop-y:${y}%;--crop-zoom:${z}%"></div>`:'';
    const disabled=active?'':' disabled title="Save or import a crop first"';
    const calibrator=item.calibratable?`<details class="crop-calibrator"${active?'':' open'}><summary>Calibrate reference crop ${origin?`· ${origin}`:''}</summary><label>X <input data-crop="x" type="range" min="0" max="100" value="${x}"></label><label>Y <input data-crop="y" type="range" min="0" max="100" value="${y}"></label><label>Zoom <input data-crop="zoom" type="range" min="100" max="700" value="${z}"></label><button data-save-crop>Save local crop</button><button data-reset-crop>${local(item.id)?'Remove local override':'Reset'}</button></details>`:'';
    return `<div class="asset-preview fidelity-preview" data-id="${item.id}" data-mode="render" data-calibrated="${active}" style="--overlay-opacity:.5"><div class="fidelity-stage">${source}<div class="fidelity-render">${render}</div>${active?'':'<div class="fidelity-missing">Calibrate or import crop</div>'}</div><span class="preview-label">RECONSTRUCTION</span><div class="fidelity-controls"><button data-fidelity="reference"${disabled}>Reference</button><button data-fidelity="overlay"${disabled}>Overlay</button><button data-fidelity="difference"${disabled}>Difference</button><button class="active" data-fidelity="render">Reconstruction</button><label>Opacity <input data-fidelity-opacity type="range" min="0" max="100" value="50"${disabled}></label></div>${calibrator}</div>`;
  }
  function workflow(){
    const done=atomEntries().filter(x=>saved(x.id)).length,total=atomEntries().length,next=atomEntries().find(x=>!saved(x.id)),sharedCount=atomEntries().filter(x=>shared(x.id)).length;
    return `<section class="calibration-workflow"><div><p class="eyebrow">ATOM CALIBRATION · V0.5</p><strong>${done}/${total} references available</strong><span>${sharedCount?`${sharedCount} shared preset${sharedCount===1?'':'s'} loaded. `:''}${done===total?'All atom crops are ready for fidelity review.':'Calibrate manually or import a compatible JSON export.'}</span></div><div class="calibration-actions"><button data-next-calibration${next?'':' disabled'}>${next?`Next: ${next.name}`:'Complete'}</button><button data-export-calibration${done?'':' disabled'}>Copy JSON</button><button data-import-calibration>Import JSON</button><input data-import-file type="file" accept="application/json,.json" hidden></div></section>`;
  }
  function rerender(){window.OpusAssetGallery.render(document.querySelector('#asset-gallery'),document.querySelector('#search-input').value)}
  async function importFile(file){
    const payload=JSON.parse(await file.text());
    if(payload.version!==1||payload.source!==references.atoms.image||!payload.assets||typeof payload.assets!=='object')throw new Error('Incompatible calibration file');
    let count=0;
    for(const item of atomEntries()){const crop=payload.assets[item.id];if(crop!==undefined){if(!validCrop(crop))throw new Error(`Invalid crop: ${item.id}`);localStorage.setItem(key(item.id),JSON.stringify({x:crop.x,y:crop.y,zoom:crop.zoom}));count++;}}
    if(!count)throw new Error('No atom calibrations found');
    return count;
  }
  function bind(container){
    container.querySelector('[data-next-calibration]')?.addEventListener('click',()=>{const next=atomEntries().find(x=>!saved(x.id));container.querySelector(`[data-id="${next?.id}"]`)?.scrollIntoView({behavior:'smooth',block:'center'});});
    container.querySelector('[data-export-calibration]')?.addEventListener('click',async e=>{const payload={version:1,source:references.atoms.image,assets:calibrations()};await navigator.clipboard.writeText(JSON.stringify(payload,null,2));e.currentTarget.textContent='Copied';setTimeout(()=>e.currentTarget.textContent='Copy JSON',1400);});
    const picker=container.querySelector('[data-import-file]');container.querySelector('[data-import-calibration]')?.addEventListener('click',()=>picker?.click());
    picker?.addEventListener('change',async e=>{const button=container.querySelector('[data-import-calibration]');try{const count=await importFile(e.target.files[0]);button.textContent=`Imported ${count}`;setTimeout(rerender,700)}catch(error){button.textContent=error.message;setTimeout(()=>button.textContent='Import JSON',1800)}finally{e.target.value=''}});
    container.querySelectorAll('.fidelity-preview').forEach(p=>{
      const ref=p.querySelector('.fidelity-reference');
      p.querySelectorAll('[data-crop]').forEach(input=>input.addEventListener('input',()=>ref?.style.setProperty(`--crop-${input.dataset.crop}`,`${input.value}%`)));
      p.querySelector('[data-save-crop]')?.addEventListener('click',()=>{const v={};p.querySelectorAll('[data-crop]').forEach(i=>v[i.dataset.crop]=Number(i.value));localStorage.setItem(key(p.dataset.id),JSON.stringify(v));rerender();});
      p.querySelector('[data-reset-crop]')?.addEventListener('click',()=>{localStorage.removeItem(key(p.dataset.id));rerender();});
      p.querySelectorAll('[data-fidelity]:not(:disabled)').forEach(b=>b.addEventListener('click',()=>{p.dataset.mode=b.dataset.fidelity;p.querySelectorAll('[data-fidelity]').forEach(x=>x.classList.toggle('active',x===b));p.querySelector('.preview-label').textContent={reference:'REFERENCE',overlay:'OVERLAY',difference:'DIFFERENCE',render:'RECONSTRUCTION'}[b.dataset.fidelity];}));
      p.querySelector('[data-fidelity-opacity]:not(:disabled)')?.addEventListener('input',e=>p.style.setProperty('--overlay-opacity',Number(e.target.value)/100));
    });
  }
  window.OpusAssetGallery={entries,references,render(container,query=''){
    const q=query.trim().toLowerCase(),visible=entries.filter(x=>!q||`${x.group} ${x.name} ${x.status} ${x.notes.join(' ')}`.toLowerCase().includes(q)),fragment=document.createDocumentFragment();
    const refs=document.createElement('section');refs.className='reference-sheets';[...new Set(visible.map(x=>x.reference))].forEach(k=>refs.appendChild(referenceCard(references[k])));if(refs.children.length)fragment.appendChild(refs);
    const intro=document.createElement('aside');intro.className='fidelity-intro';intro.innerHTML='<p class="eyebrow">FIDELITY MODE · V0.5</p><strong>Portable reference calibration.</strong><span>Local crops override shared repository presets. Import or export versioned JSON to reproduce the same seven atom alignments across browsers and contributors.</span>';fragment.appendChild(intro);
    const wf=document.createElement('div');wf.innerHTML=workflow();fragment.appendChild(wf.firstElementChild);
    const grid=document.createElement('section');grid.className='asset-comparison-grid';visible.forEach(item=>{const a=document.createElement('article');a.className='asset-card';const ref=references[item.reference];a.innerHTML=`${preview(item)}<div class="asset-caption"><div class="asset-heading"><div><p class="eyebrow">${item.group}</p><h3>${item.name}</h3></div><span class="asset-status status-${item.status}">${item.status}</span></div><a class="asset-reference-link" href="${ref.page}" target="_blank" rel="noopener noreferrer">Context source: ${ref.title}</a><h4>Validation notes</h4><ul>${item.notes.map(n=>`<li>${n}</li>`).join('')}</ul><small>OpusJS v${window.OpusJS.version}</small></div>`;grid.appendChild(a)});fragment.appendChild(grid);container.replaceChildren(fragment);bind(container);return visible.length;
  }};
})();