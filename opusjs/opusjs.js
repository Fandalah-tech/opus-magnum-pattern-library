(() => {
  const NS='http://www.w3.org/2000/svg';
  const SQRT3=Math.sqrt(3);
  let renderId=0;

  const palette={board:'#0d1211',cell:'#232c29',cellLine:'#414b47',brass:'#d3a348',brassDark:'#6a5124',metal:'#e6dcc5',shadow:'#050807'};

  const atomGeometries={
    masterAtomV1:{holderRadius:28.0,holderInset:1.7,outerCasingRadius:24.0,bevelRadius:22.65,innerCasingRadius:20.15,coreRadius:18.7,innerRingRadius:16.05,rivetOrbit:21.15,rivetRadius:.42}
  };

  const atomMaterials={
    masterMaterialV1:{
      gradient:{cx:'46%',cy:'28%',r:'88%'},
      stopLevels:[1,.89,.63,.43,.25,.12,.045],
      stopOffsets:['0%','10%','27%','49%','72%','89%','100%'],
      reflection:'masterGlassMetal'
    }
  };

  // Final canonical atom set. Shared geometry/material; only identity, optical scale and centering vary.
  const atomIdentities={
    Pb:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#73878a',ink:'#f5f5ef',mark:'♄',symbolSize:24.2,symbolX:0,symbolY:.2,symbolOpacity:.95},
    Sn:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#969477',ink:'#f5f1dc',mark:'♃',symbolSize:23.8,symbolX:.3,symbolY:.1,symbolOpacity:.94},
    Fe:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#806f73',ink:'#fff5ef',mark:'♂',symbolSize:26.6,symbolX:.2,symbolY:.5,symbolOpacity:.96},
    Cu:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#b66f48',ink:'#fff0e5',mark:'♀',symbolSize:26.3,symbolX:0,symbolY:.8,symbolOpacity:.96},
    Ag:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#bfc4c1',ink:'#ffffff',mark:'☽',symbolSize:27.2,symbolX:1.0,symbolY:-.2,symbolOpacity:.96},
    Au:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#c39a3f',ink:'#fff4c2',mark:'☉',symbolSize:23.8,symbolX:0,symbolY:.2,symbolOpacity:.96},
    Hg:{geometry:'masterAtomV1',material:'masterMaterialV1',color:'#b7b09a',gradientStops:['#e6e1d2','#d9d3c2','#beb7a2','#9f9885','#857f70','#625e53','#403d36'],ringTint:'#d7d2c4',innerRingTint:'#8f897a',ink:'#fff8e7',mark:'☿',symbolSize:25.8,symbolX:0,symbolY:.8,symbolOpacity:.95}
  };

  const el=(name,attrs={})=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));return node;};
  const axial=(q,r,size,ox,oy)=>({x:ox+size*SQRT3*(q+r/2),y:oy+size*1.5*r});
  function hexPoints(cx,cy,size){return Array.from({length:6},(_,i)=>{const a=Math.PI/180*(60*i-30);return `${cx+size*Math.cos(a)},${cy+size*Math.sin(a)}`}).join(' ')}
  function shade(hex,factor){const value=parseInt(hex.slice(1),16);const r=(value>>16)&255,g=(value>>8)&255,b=value&255;const channel=n=>Math.max(0,Math.min(255,Math.round(n*factor)));return `#${[channel(r),channel(g),channel(b)].map(n=>n.toString(16).padStart(2,'0')).join('')}`;}

  function defs(svg,id){
    const d=el('defs');
    const shadow=el('filter',{id:`shadow-${id}`,x:'-50%',y:'-50%',width:'200%',height:'200%'});
    shadow.appendChild(el('feDropShadow',{dx:0,dy:1.8,stdDeviation:2.05,'flood-color':'#000','flood-opacity':.64}));d.appendChild(shadow);
    const bevel=el('linearGradient',{id:`bevel-${id}`,x1:'8%',y1:'4%',x2:'92%',y2:'96%'});
    [['0%','#d9c19b'],['18%','#9a7650'],['47%','#46362a'],['73%','#ad8860'],['100%','#30251e']].forEach(([offset,color])=>bevel.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(bevel);
    const holder=el('linearGradient',{id:`holder-${id}`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'});
    [['0%','#73553e'],['30%','#2d241e'],['70%','#7d5d43'],['100%','#211a16']].forEach(([offset,color])=>holder.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(holder);
    const material=atomMaterials.masterMaterialV1;
    Object.entries(atomIdentities).forEach(([key,identity])=>{
      const radial=el('radialGradient',{id:`atom-${key}-${id}`,...material.gradient});
      material.stopOffsets.forEach((offset,index)=>radial.appendChild(el('stop',{offset,'stop-color':identity.gradientStops?.[index]||shade(identity.color,material.stopLevels[index])})));
      d.appendChild(radial);
    });
    svg.appendChild(d);
  }

  function drawBoard(svg,scene){if(scene.board?.visible===false)return;const {cols=8,rows=5,size=42,offsetX=66,offsetY=55}=scene.board||{};const g=el('g');for(let r=0;r<rows;r++)for(let q=0;q<cols;q++){const p=axial(q,r,size,offsetX,offsetY);g.appendChild(el('polygon',{points:hexPoints(p.x,p.y,size-2),fill:palette.cell,stroke:palette.cellLine,'stroke-width':1.1,opacity:.72}));}svg.appendChild(g);}

  function drawMaterialReflections(body){
    body.appendChild(el('ellipse',{cx:-4.6,cy:-6.4,rx:6.0,ry:2.45,fill:'#fff',opacity:.075,transform:'rotate(-18)'}));
    body.appendChild(el('ellipse',{cx:-1.5,cy:-8.0,rx:7.3,ry:3.0,fill:'#fff',opacity:.12,transform:'rotate(-12)'}));
    body.appendChild(el('ellipse',{cx:2.6,cy:-4.9,rx:9.1,ry:5.1,fill:'#fff',opacity:.055,transform:'rotate(-20)'}));
    body.appendChild(el('ellipse',{cx:5.0,cy:3.4,rx:10.9,ry:7.6,fill:'#fff',opacity:.022,transform:'rotate(-24)'}));
    body.appendChild(el('ellipse',{cx:-6.2,cy:3.8,rx:7.4,ry:10.8,fill:'#000',opacity:.20,transform:'rotate(14)'}));
    body.appendChild(el('ellipse',{cx:3.6,cy:8.8,rx:12.0,ry:5.3,fill:'#000',opacity:.24,transform:'rotate(-7)'}));
    body.appendChild(el('ellipse',{cx:8.2,cy:1.0,rx:4.5,ry:11.6,fill:'#fff',opacity:.02,transform:'rotate(27)'}));
  }

  function drawIdentity(g,identity){
    const t=el('text',{x:identity.symbolX||0,y:identity.symbolY||0,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Noto Serif Symbols 2, Segoe UI Symbol, DejaVu Sans, serif','font-size':identity.symbolSize,'font-weight':300,fill:identity.ink,'text-rendering':'geometricPrecision','pointer-events':'none',opacity:identity.symbolOpacity});
    t.textContent=identity.mark;g.appendChild(t);
  }

  function drawAtom(svg,item,scene,id){
    const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);
    const element=String(item.element||'Fe');
    const identity=atomIdentities[element]||atomIdentities.Fe;
    const geometry=atomGeometries[identity.geometry];
    const g=el('g',{transform:`translate(${p.x} ${p.y})`,'data-atom':element,'data-geometry':identity.geometry,'data-material':identity.material});
    const body=el('g',{filter:`url(#shadow-${id})`});
    body.appendChild(el('polygon',{points:hexPoints(0,0,geometry.holderRadius),fill:`url(#holder-${id})`,stroke:'#806047','stroke-width':.72}));
    body.appendChild(el('polygon',{points:hexPoints(0,0,geometry.holderRadius-geometry.holderInset),fill:'#171411',stroke:'#29211c','stroke-width':.62}));
    body.appendChild(el('circle',{r:geometry.outerCasingRadius,fill:'#090908',stroke:'#201a17','stroke-width':.96}));
    body.appendChild(el('circle',{r:geometry.bevelRadius,fill:`url(#bevel-${id})`,stroke:'#2f241d','stroke-width':.7}));
    body.appendChild(el('circle',{r:geometry.innerCasingRadius,fill:'#111513',stroke:'#070909','stroke-width':.76}));
    body.appendChild(el('circle',{r:geometry.coreRadius,fill:`url(#atom-${element}-${id})`,stroke:identity.ringTint||shade(identity.color,1.35),'stroke-width':.5}));
    body.appendChild(el('circle',{r:geometry.innerRingRadius,fill:'none',stroke:identity.innerRingTint||shade(identity.color,.3),'stroke-width':.72,opacity:.58}));
    drawMaterialReflections(body);
    for(let i=0;i<6;i++){const a=i*Math.PI/3;body.appendChild(el('circle',{cx:geometry.rivetOrbit*Math.cos(a),cy:geometry.rivetOrbit*Math.sin(a),r:geometry.rivetRadius,fill:'#3a3027',stroke:'#b99d70','stroke-width':.2,opacity:.46}));}
    g.appendChild(body);
    drawIdentity(g,identity);
    svg.appendChild(g);
  }

  function drawArm(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const angle=(item.rotation||0)*60;const len=(item.length||1)*scene.board.size*SQRT3;const g=el('g',{transform:`translate(${p.x} ${p.y}) rotate(${angle})`});g.appendChild(el('circle',{r:22,fill:palette.shadow,opacity:.5}));g.appendChild(el('circle',{r:18,fill:palette.brassDark,stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:6,fill:palette.brass}));g.appendChild(el('rect',{x:8,y:-6,width:len-16,height:12,rx:5,fill:palette.brass,stroke:palette.metal,'stroke-width':2}));g.appendChild(el('path',{d:`M${len-8},-10 L${len+8},0 L${len-8},10 Z`,fill:palette.metal,stroke:palette.brassDark,'stroke-width':2}));svg.appendChild(g);}
  function drawProjection(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:29,fill:palette.shadow,stroke:palette.brass,'stroke-width':5}));g.appendChild(el('circle',{r:21,fill:'none',stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:11,fill:'#8c236d',stroke:'#f0b7df','stroke-width':3}));for(let i=0;i<4;i++)g.appendChild(el('path',{d:'M0,-38 L6,-27 L-6,-27 Z',fill:palette.metal,transform:`rotate(${i*90})`}));svg.appendChild(g);}
  function drawBonding(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:28,fill:palette.shadow,stroke:palette.brass,'stroke-width':4}));g.appendChild(el('path',{d:'M-12,-9 L0,0 L12,-9 M-12,9 L0,0 L12,9',fill:'none',stroke:palette.metal,'stroke-width':4,'stroke-linecap':'round'}));svg.appendChild(g);}
  function drawTrack(svg,item,scene){const a=axial(item.q1,item.r1,scene.board.size,scene.board.offsetX,scene.board.offsetY);const b=axial(item.q2,item.r2,scene.board.size,scene.board.offsetX,scene.board.offsetY);svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.brassDark,'stroke-width':12,'stroke-linecap':'round'}));svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.metal,'stroke-width':3,'stroke-dasharray':'8 8','stroke-linecap':'round'}));}

  function render(scene){const width=scene.width||720,height=scene.height||360;const id=++renderId;scene.board={cols:8,rows:5,size:42,offsetX:66,offsetY:55,...scene.board};const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':scene.label||'Opus Magnum scene'});defs(svg,id);svg.appendChild(el('rect',{width,height,fill:palette.board}));drawBoard(svg,scene);(scene.tracks||[]).forEach(x=>drawTrack(svg,x,scene));(scene.glyphs||[]).forEach(x=>x.type==='projection'?drawProjection(svg,x,scene):x.type==='bonding'?drawBonding(svg,x,scene):null);(scene.arms||[]).forEach(x=>drawArm(svg,x,scene));(scene.atoms||[]).forEach(x=>drawAtom(svg,x,scene,id));return svg.outerHTML;}

  window.OpusJS={version:'1.0.1',render,axial,primitives:{atomGeometries,atomMaterials,atomIdentities}};
})();