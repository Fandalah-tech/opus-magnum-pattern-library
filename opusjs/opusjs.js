(() => {
  const NS='http://www.w3.org/2000/svg';
  const SQRT3=Math.sqrt(3);
  let renderId=0;

  const palette={board:'#0d1211',cell:'#232c29',cellLine:'#414b47',brass:'#d3a348',brassDark:'#6a5124',metal:'#e6dcc5',shadow:'#050807'};

  const atomGeometries={
    masterAtomV1:{
      holderRadius:28.0,
      holderInset:1.7,
      outerCasingRadius:24.0,
      bevelRadius:22.65,
      innerCasingRadius:20.15,
      coreRadius:18.7,
      innerRingRadius:16.05,
      rivetOrbit:21.15,
      rivetRadius:.42
    }
  };

  const atomMaterials={
    lead:{base:'#46585a',mid:'#6f7f7c',dark:'#202d2e',light:'#c2ccca',ink:'#f5f5ef',gradient:{cx:'43%',cy:'34%',r:'82%'},reflection:'leadGlass'},
    tin:{base:'#8b5d43',mid:'#b17c59',dark:'#482f24',light:'#d8b18d',ink:'#f5e7d9',gradient:{cx:'39%',cy:'29%',r:'81%'},reflection:'tinMetal'},
    iron:{base:'#777e83',mid:'#a3a9ad',dark:'#3d4246',light:'#d1d5d6',ink:'#f0f0ec',gradient:{cx:'43%',cy:'24%',r:'78%'},reflection:'standard'},
    copper:{base:'#9b5934',mid:'#c77b4b',dark:'#5a301e',light:'#e5a574',ink:'#f7e8dd',gradient:{cx:'43%',cy:'24%',r:'78%'},reflection:'standard'},
    silver:{base:'#a7aaa3',mid:'#d4d5cf',dark:'#60645f',light:'#f0efe8',ink:'#ffffff',gradient:{cx:'43%',cy:'24%',r:'78%'},reflection:'standard'},
    gold:{base:'#a98425',mid:'#d4ad42',dark:'#5f4816',light:'#f1d77c',ink:'#fff4c2',gradient:{cx:'43%',cy:'24%',r:'78%'},reflection:'standard'},
    mercury:{base:'#8699a1',mid:'#b8c7cc',dark:'#4d6068',light:'#dce8eb',ink:'#f5fbfc',gradient:{cx:'43%',cy:'24%',r:'78%'},reflection:'standard'}
  };

  const atomIdentities={
    Pb:{geometry:'masterAtomV1',material:'lead',mark:'♄',symbolSize:21.2,symbolY:0,symbolOpacity:.95},
    Sn:{geometry:'masterAtomV1',material:'tin',mark:'♃',symbolSize:20.0,symbolY:0,symbolOpacity:.95},
    Fe:{geometry:'masterAtomV1',material:'iron',mark:'♂',symbolSize:18.2,symbolY:-.1,symbolOpacity:.96},
    Cu:{geometry:'masterAtomV1',material:'copper',mark:'♀',symbolSize:18.2,symbolY:-.1,symbolOpacity:.96},
    Ag:{geometry:'masterAtomV1',material:'silver',mark:'☽',symbolSize:18.2,symbolY:-.1,symbolOpacity:.96},
    Au:{geometry:'masterAtomV1',material:'gold',mark:'☉',symbolSize:18.2,symbolY:-.1,symbolOpacity:.96},
    Hg:{geometry:'masterAtomV1',material:'mercury',mark:'☿',symbolSize:18.2,symbolY:-.1,symbolOpacity:.96}
  };

  const el=(name,attrs={})=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));return node;};
  const axial=(q,r,size,ox,oy)=>({x:ox+size*SQRT3*(q+r/2),y:oy+size*1.5*r});
  function hexPoints(cx,cy,size){return Array.from({length:6},(_,i)=>{const a=Math.PI/180*(60*i-30);return `${cx+size*Math.cos(a)},${cy+size*Math.sin(a)}`}).join(' ')}

  function defs(svg,id){
    const d=el('defs');
    const shadow=el('filter',{id:`shadow-${id}`,x:'-50%',y:'-50%',width:'200%',height:'200%'});
    shadow.appendChild(el('feDropShadow',{dx:0,dy:1.8,stdDeviation:2.05,'flood-color':'#000','flood-opacity':.64}));d.appendChild(shadow);
    const bevel=el('linearGradient',{id:`bevel-${id}`,x1:'8%',y1:'4%',x2:'92%',y2:'96%'});
    [['0%','#d9c19b'],['18%','#9a7650'],['47%','#46362a'],['73%','#ad8860'],['100%','#30251e']].forEach(([offset,color])=>bevel.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(bevel);
    const holder=el('linearGradient',{id:`holder-${id}`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'});
    [['0%','#73553e'],['30%','#2d241e'],['70%','#7d5d43'],['100%','#211a16']].forEach(([offset,color])=>holder.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(holder);
    Object.entries(atomMaterials).forEach(([key,material])=>{
      const radial=el('radialGradient',{id:`atom-material-${key}-${id}`,...material.gradient});
      [['0%',material.light],['24%',material.mid],['64%',material.base],['100%',material.dark]].forEach(([offset,color])=>radial.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(radial);
    });
    svg.appendChild(d);
  }

  function drawBoard(svg,scene){if(scene.board?.visible===false)return;const {cols=8,rows=5,size=42,offsetX=66,offsetY=55}=scene.board||{};const g=el('g');for(let r=0;r<rows;r++)for(let q=0;q<cols;q++){const p=axial(q,r,size,offsetX,offsetY);g.appendChild(el('polygon',{points:hexPoints(p.x,p.y,size-2),fill:palette.cell,stroke:palette.cellLine,'stroke-width':1.1,opacity:.72}));}svg.appendChild(g);}

  function drawMaterialReflections(body,profile){
    body.appendChild(el('ellipse',{cx:-4.6,cy:-6.4,rx:6.0,ry:2.45,fill:'#fff',opacity:.075,transform:'rotate(-18)'}));
    if(profile==='leadGlass'){
      body.appendChild(el('ellipse',{cx:3.2,cy:4.8,rx:10.6,ry:6.6,fill:'#d8e1df',opacity:.045,transform:'rotate(-22)'}));
      body.appendChild(el('ellipse',{cx:-5.0,cy:3.0,rx:7.2,ry:10.0,fill:'#142225',opacity:.16,transform:'rotate(16)'}));
      body.appendChild(el('ellipse',{cx:5.6,cy:-1.0,rx:5.8,ry:11.4,fill:'#f4f6f1',opacity:.035,transform:'rotate(30)'}));
    }else if(profile==='tinMetal'){
      body.appendChild(el('ellipse',{cx:3.8,cy:4.2,rx:10.0,ry:6.1,fill:'#f0cfad',opacity:.055,transform:'rotate(-24)'}));
      body.appendChild(el('ellipse',{cx:-5.2,cy:3.1,rx:6.6,ry:9.4,fill:'#291a14',opacity:.13,transform:'rotate(17)'}));
      body.appendChild(el('ellipse',{cx:5.0,cy:-2.0,rx:4.8,ry:10.2,fill:'#fff1df',opacity:.035,transform:'rotate(28)'}));
    }
  }

  function drawAtom(svg,item,scene,id){
    const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);
    const element=String(item.element||'Fe');
    const identity=atomIdentities[element]||atomIdentities.Fe;
    const geometry=atomGeometries[identity.geometry];
    const material=atomMaterials[identity.material];
    const g=el('g',{transform:`translate(${p.x} ${p.y})`,'data-atom':element,'data-geometry':identity.geometry,'data-material':identity.material});
    const body=el('g',{filter:`url(#shadow-${id})`});
    body.appendChild(el('polygon',{points:hexPoints(0,0,geometry.holderRadius),fill:`url(#holder-${id})`,stroke:'#806047','stroke-width':.72}));
    body.appendChild(el('polygon',{points:hexPoints(0,0,geometry.holderRadius-geometry.holderInset),fill:'#171411',stroke:'#29211c','stroke-width':.62}));
    body.appendChild(el('circle',{r:geometry.outerCasingRadius,fill:'#090908',stroke:'#201a17','stroke-width':.96}));
    body.appendChild(el('circle',{r:geometry.bevelRadius,fill:`url(#bevel-${id})`,stroke:'#2f241d','stroke-width':.7}));
    body.appendChild(el('circle',{r:geometry.innerCasingRadius,fill:'#111513',stroke:'#070909','stroke-width':.76}));
    body.appendChild(el('circle',{r:geometry.coreRadius,fill:`url(#atom-material-${identity.material}-${id})`,stroke:material.light,'stroke-width':.5}));
    body.appendChild(el('circle',{r:geometry.innerRingRadius,fill:'none',stroke:material.dark,'stroke-width':.72,opacity:.58}));
    drawMaterialReflections(body,material.reflection);
    for(let i=0;i<6;i++){const a=i*Math.PI/3;body.appendChild(el('circle',{cx:geometry.rivetOrbit*Math.cos(a),cy:geometry.rivetOrbit*Math.sin(a),r:geometry.rivetRadius,fill:'#3a3027',stroke:'#b99d70','stroke-width':.2,opacity:.46}));}
    g.appendChild(body);
    const t=el('text',{x:0,y:identity.symbolY,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Noto Serif Symbols 2, Segoe UI Symbol, DejaVu Sans, serif','font-size':identity.symbolSize,'font-weight':300,fill:material.ink,'text-rendering':'geometricPrecision','pointer-events':'none',opacity:identity.symbolOpacity});
    t.textContent=identity.mark;
    g.appendChild(t);
    svg.appendChild(g);
  }

  function drawArm(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const angle=(item.rotation||0)*60;const len=(item.length||1)*scene.board.size*SQRT3;const g=el('g',{transform:`translate(${p.x} ${p.y}) rotate(${angle})`});g.appendChild(el('circle',{r:22,fill:palette.shadow,opacity:.5}));g.appendChild(el('circle',{r:18,fill:palette.brassDark,stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:6,fill:palette.brass}));g.appendChild(el('rect',{x:8,y:-6,width:len-16,height:12,rx:5,fill:palette.brass,stroke:palette.metal,'stroke-width':2}));g.appendChild(el('path',{d:`M${len-8},-10 L${len+8},0 L${len-8},10 Z`,fill:palette.metal,stroke:palette.brassDark,'stroke-width':2}));svg.appendChild(g);}
  function drawProjection(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:29,fill:palette.shadow,stroke:palette.brass,'stroke-width':5}));g.appendChild(el('circle',{r:21,fill:'none',stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:11,fill:'#8c236d',stroke:'#f0b7df','stroke-width':3}));for(let i=0;i<4;i++)g.appendChild(el('path',{d:'M0,-38 L6,-27 L-6,-27 Z',fill:palette.metal,transform:`rotate(${i*90})`}));svg.appendChild(g);}
  function drawBonding(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:28,fill:palette.shadow,stroke:palette.brass,'stroke-width':4}));g.appendChild(el('path',{d:'M-12,-9 L0,0 L12,-9 M-12,9 L0,0 L12,9',fill:'none',stroke:palette.metal,'stroke-width':4,'stroke-linecap':'round'}));svg.appendChild(g);}
  function drawTrack(svg,item,scene){const a=axial(item.q1,item.r1,scene.board.size,scene.board.offsetX,scene.board.offsetY);const b=axial(item.q2,item.r2,scene.board.size,scene.board.offsetX,scene.board.offsetY);svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.brassDark,'stroke-width':12,'stroke-linecap':'round'}));svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.metal,'stroke-width':3,'stroke-dasharray':'8 8','stroke-linecap':'round'}));}

  function render(scene){const width=scene.width||720,height=scene.height||360;const id=++renderId;scene.board={cols:8,rows:5,size:42,offsetX:66,offsetY:55,...scene.board};const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':scene.label||'Opus Magnum scene'});defs(svg,id);svg.appendChild(el('rect',{width,height,fill:palette.board}));drawBoard(svg,scene);(scene.tracks||[]).forEach(x=>drawTrack(svg,x,scene));(scene.glyphs||[]).forEach(x=>x.type==='projection'?drawProjection(svg,x,scene):x.type==='bonding'?drawBonding(svg,x,scene):null);(scene.arms||[]).forEach(x=>drawArm(svg,x,scene));(scene.atoms||[]).forEach(x=>drawAtom(svg,x,scene,id));return svg.outerHTML;}

  window.OpusJS={version:'0.7.0',render,axial,primitives:{atomGeometries,atomMaterials,atomIdentities}};
})();