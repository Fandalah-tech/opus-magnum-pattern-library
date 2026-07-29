(() => {
  const NS='http://www.w3.org/2000/svg';
  const SQRT3=Math.sqrt(3);
  let renderId=0;
  const palette={board:'#0d1211',cell:'#232c29',cellLine:'#414b47',brass:'#d3a348',brassDark:'#6a5124',metal:'#e6dcc5',shadow:'#050807'};
  const elements={
    Pb:{base:'#52636a',mid:'#73858a',dark:'#26343a',light:'#b7c4c5',ink:'#eef2ee',mark:'♄'},
    Sn:{base:'#996844',mid:'#bd8a62',dark:'#573721',light:'#dfb68e',ink:'#f4e7d8',mark:'♃'},
    Fe:{base:'#777e83',mid:'#a3a9ad',dark:'#3d4246',light:'#d1d5d6',ink:'#f0f0ec',mark:'♂'},
    Cu:{base:'#9b5934',mid:'#c77b4b',dark:'#5a301e',light:'#e5a574',ink:'#f7e8dd',mark:'♀'},
    Ag:{base:'#a7aaa3',mid:'#d4d5cf',dark:'#60645f',light:'#f0efe8',ink:'#ffffff',mark:'☽'},
    Au:{base:'#a98425',mid:'#d4ad42',dark:'#5f4816',light:'#f1d77c',ink:'#fff4c2',mark:'☉'},
    Hg:{base:'#8699a1',mid:'#b8c7cc',dark:'#4d6068',light:'#dce8eb',ink:'#f5fbfc',mark:'☿'}
  };
  const el=(name,attrs={})=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));return node;};
  const axial=(q,r,size,ox,oy)=>({x:ox+size*SQRT3*(q+r/2),y:oy+size*1.5*r});
  function hexPoints(cx,cy,size){return Array.from({length:6},(_,i)=>{const a=Math.PI/180*(60*i-30);return `${cx+size*Math.cos(a)},${cy+size*Math.sin(a)}`}).join(' ')}
  function defs(svg,id){
    const d=el('defs');
    const shadow=el('filter',{id:`shadow-${id}`,x:'-50%',y:'-50%',width:'200%',height:'200%'});
    shadow.appendChild(el('feDropShadow',{dx:0,dy:2.2,stdDeviation:2.4,'flood-color':'#000','flood-opacity':.68}));d.appendChild(shadow);
    const bevel=el('linearGradient',{id:`bevel-${id}`,x1:'8%',y1:'4%',x2:'92%',y2:'96%'});
    [['0%','#e5d3b2'],['18%','#a98258'],['46%','#51402f'],['72%','#c3a274'],['100%','#3f3025']].forEach(([offset,color])=>bevel.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(bevel);
    const holder=el('linearGradient',{id:`holder-${id}`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'});
    [['0%','#725943'],['32%','#2f2823'],['70%','#85664a'],['100%','#211b18']].forEach(([offset,color])=>holder.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(holder);
    Object.entries(elements).forEach(([symbol,c])=>{
      const radial=el('radialGradient',{id:`atom-${symbol}-${id}`,cx:'37%',cy:'24%',r:'78%'});
      [['0%',c.light],['26%',c.mid],['66%',c.base],['100%',c.dark]].forEach(([offset,color])=>radial.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(radial);
    });
    svg.appendChild(d);
  }
  function drawBoard(svg,scene){if(scene.board?.visible===false)return;const {cols=8,rows=5,size=42,offsetX=66,offsetY=55}=scene.board||{};const g=el('g');for(let r=0;r<rows;r++)for(let q=0;q<cols;q++){const p=axial(q,r,size,offsetX,offsetY);g.appendChild(el('polygon',{points:hexPoints(p.x,p.y,size-2),fill:palette.cell,stroke:palette.cellLine,'stroke-width':1.1,opacity:.72}));}svg.appendChild(g);}
  function drawAtom(svg,item,scene,id){
    const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);
    const element=String(item.element||'Fe');
    const c=elements[element]||elements.Fe;
    const g=el('g',{transform:`translate(${p.x} ${p.y})`,'data-atom':element});
    const body=el('g',{filter:`url(#shadow-${id})`});
    body.appendChild(el('polygon',{points:hexPoints(0,0,28.2),fill:`url(#holder-${id})`,stroke:'#8f6d50','stroke-width':.9}));
    body.appendChild(el('polygon',{points:hexPoints(0,0,26.2),fill:'#171512',stroke:'#2a231f','stroke-width':.8}));
    body.appendChild(el('circle',{r:24.7,fill:'#080908',stroke:'#211c18','stroke-width':1.15}));
    body.appendChild(el('circle',{r:23.1,fill:`url(#bevel-${id})`,stroke:'#2f241d','stroke-width':.9}));
    body.appendChild(el('circle',{r:20.9,fill:'#131715',stroke:'#070909','stroke-width':1}));
    body.appendChild(el('circle',{r:19.4,fill:`url(#atom-${element}-${id})`,stroke:c.light,'stroke-width':.68}));
    body.appendChild(el('circle',{r:16.8,fill:'none',stroke:c.dark,'stroke-width':.88,opacity:.68}));
    body.appendChild(el('ellipse',{cx:-5.2,cy:-7.4,rx:7.1,ry:3.1,fill:'#fff',opacity:.1,transform:'rotate(-18)'}));
    for(let i=0;i<6;i++){const a=i*Math.PI/3;body.appendChild(el('circle',{cx:21.55*Math.cos(a),cy:21.55*Math.sin(a),r:.66,fill:'#29241e',stroke:'#c4ad84','stroke-width':.34,opacity:.62}));}
    g.appendChild(body);
    const t=el('text',{x:0,y:.05,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Segoe UI Symbol, Noto Sans Symbols 2, DejaVu Sans, serif','font-size':18.8,'font-weight':300,fill:c.ink,stroke:'#626a69','stroke-width':.1,'paint-order':'stroke fill','stroke-linejoin':'round','text-rendering':'geometricPrecision','pointer-events':'none',opacity:.92});
    t.textContent=c.mark;
    g.appendChild(t);
    svg.appendChild(g);
  }
  function drawArm(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const angle=(item.rotation||0)*60;const len=(item.length||1)*scene.board.size*SQRT3;const g=el('g',{transform:`translate(${p.x} ${p.y}) rotate(${angle})`});g.appendChild(el('circle',{r:22,fill:palette.shadow,opacity:.5}));g.appendChild(el('circle',{r:18,fill:palette.brassDark,stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:6,fill:palette.brass}));g.appendChild(el('rect',{x:8,y:-6,width:len-16,height:12,rx:5,fill:palette.brass,stroke:palette.metal,'stroke-width':2}));g.appendChild(el('path',{d:`M${len-8},-10 L${len+8},0 L${len-8},10 Z`,fill:palette.metal,stroke:palette.brassDark,'stroke-width':2}));svg.appendChild(g);}
  function drawProjection(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:29,fill:palette.shadow,stroke:palette.brass,'stroke-width':5}));g.appendChild(el('circle',{r:21,fill:'none',stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:11,fill:'#8c236d',stroke:'#f0b7df','stroke-width':3}));for(let i=0;i<4;i++)g.appendChild(el('path',{d:'M0,-38 L6,-27 L-6,-27 Z',fill:palette.metal,transform:`rotate(${i*90})`}));svg.appendChild(g);}
  function drawBonding(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:28,fill:palette.shadow,stroke:palette.brass,'stroke-width':4}));g.appendChild(el('path',{d:'M-12,-9 L0,0 L12,-9 M-12,9 L0,0 L12,9',fill:'none',stroke:palette.metal,'stroke-width':4,'stroke-linecap':'round'}));svg.appendChild(g);}
  function drawTrack(svg,item,scene){const a=axial(item.q1,item.r1,scene.board.size,scene.board.offsetX,scene.board.offsetY);const b=axial(item.q2,item.r2,scene.board.size,scene.board.offsetX,scene.board.offsetY);svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.brassDark,'stroke-width':12,'stroke-linecap':'round'}));svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.metal,'stroke-width':3,'stroke-dasharray':'8 8','stroke-linecap':'round'}));}
  function render(scene){const width=scene.width||720,height=scene.height||360;const id=++renderId;scene.board={cols:8,rows:5,size:42,offsetX:66,offsetY:55,...scene.board};const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':scene.label||'Opus Magnum scene'});defs(svg,id);svg.appendChild(el('rect',{width,height,fill:palette.board}));drawBoard(svg,scene);(scene.tracks||[]).forEach(x=>drawTrack(svg,x,scene));(scene.glyphs||[]).forEach(x=>x.type==='projection'?drawProjection(svg,x,scene):x.type==='bonding'?drawBonding(svg,x,scene):null);(scene.arms||[]).forEach(x=>drawArm(svg,x,scene));(scene.atoms||[]).forEach(x=>drawAtom(svg,x,scene,id));return svg.outerHTML;}
  window.OpusJS={version:'0.3.1',render,axial};
})();