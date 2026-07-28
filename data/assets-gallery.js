(() => {
  const board={cols:5,rows:3,size:38,offsetX:62,offsetY:58};
  const atomTypes=['Pb','Sn','Fe','Cu','Ag','Au','Hg'];
  const entries=[
    ...atomTypes.map(element=>({group:'Atoms',name:element,scene:{width:420,height:250,board,atoms:[{element,q:2,r:1}]}})),
    {group:'Mechanisms',name:'Arm — length 1',scene:{width:420,height:250,board,arms:[{q:1,r:1,length:1,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 2',scene:{width:420,height:250,board,arms:[{q:0,r:1,length:2,rotation:0}]}},
    {group:'Mechanisms',name:'Arm — length 3',scene:{width:420,height:250,board,arms:[{q:0,r:1,length:3,rotation:0}]}},
    {group:'Glyphs',name:'Glyph of Projection',scene:{width:420,height:250,board,glyphs:[{type:'projection',q:2,r:1}]}},
    {group:'Glyphs',name:'Glyph of Bonding',scene:{width:420,height:250,board,glyphs:[{type:'bonding',q:2,r:1}]}},
    {group:'Tracks',name:'Straight Track',scene:{width:420,height:250,board,tracks:[{q1:0,r1:1,q2:3,r2:1}]}},
    {group:'Board',name:'Hexagonal board background',scene:{width:420,height:250,board}}
  ];
  window.OpusAssetGallery={
    entries,
    render(container,query=''){
      const q=query.trim().toLowerCase();
      const visible=entries.filter(x=>!q||`${x.group} ${x.name}`.toLowerCase().includes(q));
      container.replaceChildren(...visible.map(item=>{
        const article=document.createElement('article');
        article.className='asset-card';
        article.innerHTML=`<div class="asset-preview">${window.OpusJS.render({...item.scene,label:item.name})}</div><div class="asset-caption"><p class="eyebrow">${item.group}</p><h3>${item.name}</h3><small>OpusJS v${window.OpusJS.version} · validation pending</small></div>`;
        return article;
      }));
      return visible.length;
    }
  };
})();