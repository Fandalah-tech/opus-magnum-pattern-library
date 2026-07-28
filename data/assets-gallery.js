(() => {
  const board={cols:5,rows:3,size:38,offsetX:62,offsetY:58};
  const references={
    atoms:{
      title:'Atom layout — production reference',
      image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/48f7201e-226e-4949-a318-348c4ca2d34c/atom_layout_B_1200.png',
      page:'https://www.kylesteed.net/opus-magnum',
      credit:'Kyle Steed · Opus Magnum production art'
    },
    parts:{
      title:'Parts layout — production reference',
      image:'https://images.squarespace-cdn.com/content/v1/52917573e4b03e7a0728e5b3/63013d2b-70b4-4d59-88bb-56a94203e11a/parts_layout_withFrame_1200.png',
      page:'https://www.kylesteed.net/opus-magnum',
      credit:'Kyle Steed · Opus Magnum production art'
    }
  };
  const atomTypes=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const atomNotes=['Outer construction is too simple','Material depth and highlights are missing','Symbol scale and type treatment need comparison'];
  const entries=[
    ...atomTypes.map(element=>({group:'Atoms',name:element,status:'draft',reference:'atoms',notes:atomNotes,scene:{width:420,height:250,board,atoms:[{element,q:2,r:1}]}})),
    {group:'Mechanisms',name:'Arm — length 1',status:'draft',reference:'parts',notes:['Pivot assembly needs canonical layered construction','Arm body and grabber geometry are placeholders','Metal shading is too flat'],scene:{width:420,height:250,board,arms:[{q:1,r:1,length:1,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 2',status:'draft',reference:'parts',notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:2,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 3',status:'draft',reference:'parts',notes:['Segment spacing must match the game','Pivot and grabber need canonical proportions'],scene:{width:420,height:250,board,arms:[{q:0,r:1,length:3,rotation:0}]}},
    {group:'Glyphs',name:'Glyph of Projection',status:'draft',reference:'parts',notes:['Current radial form is not canonical','Internal material and rune geometry must be rebuilt','Scale relative to one hex needs verification'],scene:{width:420,height:250,board,glyphs:[{type:'projection',q:2,r:1}]}},
    {group:'Glyphs',name:'Glyph of Bonding',status:'draft',reference:'parts',notes:['Current symbol is only a semantic placeholder','Canonical plate and bonding marks are missing'],scene:{width:420,height:250,board,glyphs:[{type:'bonding',q:2,r:1}]}},
    {group:'Tracks',name:'Straight Track',status:'draft',reference:'parts',notes:['Rail construction and nodes need canonical geometry','Current dashed line is not visually faithful'],scene:{width:420,height:250,board,tracks:[{q1:0,r1:1,q2:3,r2:1}]}},
    {group:'Board',name:'Hexagonal board background',status:'draft',reference:'parts',notes:['Hex borders are too prominent','Surface lacks material depth and vignette','Spacing and perspective require comparison'],scene:{width:420,height:250,board}}
  ];
  function referenceCard(ref){
    const section=document.createElement('article');
    section.className='reference-sheet';
    section.innerHTML=`<a href="${ref.page}" target="_blank" rel="noopener noreferrer"><img src="${ref.image}" alt="${ref.title}" loading="lazy"></a><div><p class="eyebrow">PRIMARY REFERENCE</p><h3>${ref.title}</h3><small>${ref.credit}. Displayed for comparison only; not packaged with OpusJS.</small></div>`;
    return section;
  }
  window.OpusAssetGallery={
    entries,references,
    render(container,query=''){
      const q=query.trim().toLowerCase();
      const visible=entries.filter(x=>!q||`${x.group} ${x.name} ${x.status} ${x.notes.join(' ')}`.toLowerCase().includes(q));
      const fragment=document.createDocumentFragment();
      const shownRefs=[...new Set(visible.map(x=>x.reference))];
      if(shownRefs.length){
        const refs=document.createElement('section');refs.className='reference-sheets';
        shownRefs.forEach(key=>refs.appendChild(referenceCard(references[key])));
        fragment.appendChild(refs);
      }
      const grid=document.createElement('section');grid.className='asset-comparison-grid';
      visible.forEach(item=>{
        const article=document.createElement('article');
        article.className='asset-card';
        const ref=references[item.reference];
        article.innerHTML=`<div class="asset-preview"><span class="preview-label">OPUSJS RENDER</span>${window.OpusJS.render({...item.scene,label:item.name})}</div><div class="asset-caption"><div class="asset-heading"><div><p class="eyebrow">${item.group}</p><h3>${item.name}</h3></div><span class="asset-status status-${item.status}">${item.status}</span></div><a class="asset-reference-link" href="${ref.page}" target="_blank" rel="noopener noreferrer">Reference: ${ref.title}</a><h4>Validation notes</h4><ul>${item.notes.map(note=>`<li>${note}</li>`).join('')}</ul><small>OpusJS v${window.OpusJS.version}</small></div>`;
        grid.appendChild(article);
      });
      fragment.appendChild(grid);container.replaceChildren(fragment);
      return visible.length;
    }
  };
})();