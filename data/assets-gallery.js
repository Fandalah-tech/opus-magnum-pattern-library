(() => {
  const board={cols:5,rows:3,size:38,offsetX:62,offsetY:58};
  const references={
    atoms:{title:'Atom layout — production reference',image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/48f7201e-226e-4949-a318-348c4ca2d34c/atom_layout_B_1200.png',page:'https://www.kylesteed.net/opus-magnum',credit:'Kyle Steed · Opus Magnum production art'},
    parts:{title:'Parts layout — production reference',image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/63013d2b-70b4-4d59-88bb-56a94203e11a/parts_layout_withFrame_1200.png',page:'https://www.kylesteed.net/opus-magnum',credit:'Kyle Steed · Opus Magnum production art'}
  };
  const atomTypes=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const atomNotes=['Layered rim, recessed core and material highlight added in v0.2','Isolated game reference still required before overlay calibration','Confirm alchemical symbol weight, scale and material-specific hue'];
  const entries=[
    ...atomTypes.map(element=>({group:'Atoms',name:element,status:'draft',reference:'atoms',isolatedReference:null,notes:atomNotes,scene:{width:420,height:250,board,atoms:[{element,q:2,r:1}]}})),
    {group:'Mechanisms',name:'Arm — length 1',status:'draft',reference:'parts',isolatedReference:null,notes:['Pivot assembly needs canonical layered construction','Arm body and grabber geometry are placeholders','Metal shading is too flat'],scene:{width:420,height:250,board,arms:[{q:1,r:1,length:1,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 2',status:'draft',reference:'parts',isolatedReference:null,notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:2,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 3',status:'draft',reference:'parts',isolatedReference:null,notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:3,rotation:0}]}},
    {group:'Glyphs',name:'Glyph of Projection',status:'draft',reference:'parts',isolatedReference:null,notes:['Current radial form is not canonical','Internal material and rune geometry must be rebuilt','Scale relative to one hex needs verification'],scene:{width:420,height:250,board,glyphs:[{type:'projection',q:2,r:1}]}},
    {group:'Glyphs',name:'Glyph of Bonding',status:'draft',reference:'parts',isolatedReference:null,notes:['Current symbol is only a semantic placeholder','Canonical plate and bonding marks are missing'],scene:{width:420,height:250,board,glyphs:[{type:'bonding',q:2,r:1}]}},
    {group:'Tracks',name:'Straight Track',status:'draft',reference:'parts',isolatedReference:null,notes:['Rail construction and nodes need canonical geometry','Current dashed line is not visually faithful'],scene:{width:420,height:250,board,tracks:[{q1:0,r1:1,q2:3,r2:1}]}},
    {group:'Board',name:'Hexagonal board background',status:'draft',reference:'parts',isolatedReference:null,notes:['Hex borders are too prominent','Surface lacks material depth and vignette','Spacing and perspective require comparison'],scene:{width:420,height:250,board}}
  ];
  function referenceCard(ref){const section=document.createElement('article');section.className='reference-sheet';section.innerHTML=`<a href="${ref.page}" target="_blank" rel="noopener noreferrer"><img src="${ref.image}" alt="${ref.title}" loading="lazy"></a><div><p class="eyebrow">CONTEXT REFERENCE</p><h3>${ref.title}</h3><small>${ref.credit}. Context only: this full sheet is not used for pixel overlay.</small></div>`;return section;}
  function fidelityPreview(item){
    const render=window.OpusJS.render({...item.scene,label:item.name});
    const calibrated=Boolean(item.isolatedReference?.image);
    const reference=calibrated?`<img class="fidelity-reference" src="${item.isolatedReference.image}" alt="Isolated reference for ${item.name}" loading="lazy">`:'';
    const disabled=calibrated?'':' disabled title="Requires an isolated, calibrated reference"';
    const notice=calibrated?'':'<div class="fidelity-missing">Isolated reference required</div>';
    return `<div class="asset-preview fidelity-preview" data-mode="render" data-calibrated="${calibrated}" style="--overlay-opacity:.5"><div class="fidelity-stage">${reference}<div class="fidelity-render">${render}</div>${notice}</div><span class="preview-label">RECONSTRUCTION</span><div class="fidelity-controls" role="group" aria-label="Fidelity comparison mode"><button data-fidelity="reference"${disabled}>Reference</button><button data-fidelity="overlay"${disabled}>Overlay</button><button data-fidelity="difference"${disabled}>Difference</button><button class="active" data-fidelity="render">Reconstruction</button><label>Opacity <input data-fidelity-opacity type="range" min="0" max="100" value="50"${disabled}></label></div></div>`;
  }
  function bindFidelity(container){container.querySelectorAll('.fidelity-preview').forEach(preview=>{preview.querySelectorAll('[data-fidelity]:not(:disabled)').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.fidelity;preview.dataset.mode=mode;preview.querySelectorAll('[data-fidelity]').forEach(x=>x.classList.toggle('active',x===button));const labels={reference:'REFERENCE',overlay:'OVERLAY 50%',difference:'DIFFERENCE',render:'RECONSTRUCTION'};preview.querySelector('.preview-label').textContent=labels[mode];}));const opacity=preview.querySelector('[data-fidelity-opacity]');if(!opacity.disabled)opacity.addEventListener('input',event=>{preview.style.setProperty('--overlay-opacity',Number(event.target.value)/100);if(preview.dataset.mode==='overlay')preview.querySelector('.preview-label').textContent=`OVERLAY ${event.target.value}%`;});});}
  window.OpusAssetGallery={entries,references,render(container,query=''){
    const q=query.trim().toLowerCase();
    const visible=entries.filter(x=>!q||`${x.group} ${x.name} ${x.status} ${x.notes.join(' ')}`.toLowerCase().includes(q));
    const fragment=document.createDocumentFragment();
    const shownRefs=[...new Set(visible.map(x=>x.reference))];
    if(shownRefs.length){const refs=document.createElement('section');refs.className='reference-sheets';shownRefs.forEach(key=>refs.appendChild(referenceCard(references[key])));fragment.appendChild(refs);}
    const intro=document.createElement('aside');intro.className='fidelity-intro';intro.innerHTML='<p class="eyebrow">FIDELITY MODE · V0.2</p><strong>Only isolated references may be overlaid.</strong><span>Full production sheets remain contextual sources. Reference, Overlay and Difference stay disabled until an asset-specific image has been cropped, aligned and documented.</span>';fragment.appendChild(intro);
    const grid=document.createElement('section');grid.className='asset-comparison-grid';
    visible.forEach(item=>{const article=document.createElement('article');article.className='asset-card';const ref=references[item.reference];article.innerHTML=`${fidelityPreview(item)}<div class="asset-caption"><div class="asset-heading"><div><p class="eyebrow">${item.group}</p><h3>${item.name}</h3></div><span class="asset-status status-${item.status}">${item.status}</span></div><a class="asset-reference-link" href="${ref.page}" target="_blank" rel="noopener noreferrer">Context source: ${ref.title}</a><h4>Validation notes</h4><ul>${item.notes.map(note=>`<li>${note}</li>`).join('')}</ul><small>OpusJS v${window.OpusJS.version}</small></div>`;grid.appendChild(article);});
    fragment.appendChild(grid);container.replaceChildren(fragment);bindFidelity(container);return visible.length;
  }};
})();