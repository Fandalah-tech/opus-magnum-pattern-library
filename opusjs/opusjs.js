(() => {
  const NS='http://www.w3.org/2000/svg';
  const SQRT3=Math.sqrt(3);
  let renderId=0;
  const palette={board:'#0d1211',cell:'#232c29',cellLine:'#414b47',brass:'#d3a348',brassDark:'#6a5124',metal:'#e6dcc5',shadow:'#050807'};
  const elements={
    Pb:{base:'#74805a',mid:'#9aa877',dark:'#37402e',light:'#c4cba8',ink:'#20251c'},
    Sn:{base:'#996844',mid:'#bd8a62',dark:'#573721',light:'#dfb68e',ink:'#2f2117'},
    Fe:{base:'#777e83',mid:'#a3a9ad',dark:'#3d4246',light:'#d1d5d6',ink:'#202326'},
    Cu:{base:'#9b5934',mid:'#c77b4b',dark:'#5a301e',light:'#e5a574',ink:'#321b12'},
    Ag:{base:'#a7aaa3',mid:'#d4d5cf',dark:'#60645f',light:'#f0efe8',ink:'#353834'},
    Au:{base:'#a98425',mid:'#d4ad42',dark:'#5f4816',light:'#f1d77c',ink:'#342b12'},
    Hg:{base:'#8699a1',mid:'#b8c7cc',dark:'#4d6068',light:'#dce8eb',ink:'#263238'}
  };
  const el=(name,attrs={})=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));return node;};
  const axial=(q,r,size,ox,oy)=>({x:ox+size*SQRT3*(q+r/2),y:oy+size*1.5*r});
  function hexPoints(cx,cy,size){return Array.from({length:6},(_,i)=>{const a=Math.PI/180*(60*i-30);return `${cx+size*Math.cos(a)},${cy+size*Math.sin(a)}`}).join(' ')}
  function defs(svg,id){
    const d=el('defs');
    const shadow=el('filter',{id:`shadow-${id}`,x:'-50%',y:'-50%',width:'200%',height:'200%'});
    shadow.appendChild(el('feDropShadow',{dx:0,dy:3,stdDeviation:3,'flood-color':'#000','flood-opacity':.7}));d.appendChild(shadow);
    const bevel=el('linearGradient',{id:`bevel-${id}`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'});
    [['0%','#fff3d4'],['22%','#c9b98f'],['50%','#6f674f'],['76%','#e9dfc5'],['100%','#7c7258']].forEach(([offset,color])=>bevel.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(bevel);
    Object.entries(elements).forEach(([symbol,c])=>{
      const radial=el('radialGradient',{id:`atom-${symbol}-${id}`,cx:'36%',cy:'28%',r:'72%'});
      [['0%',c.light],['34%',c.mid],['72%',c.base],['100%',c.dark]].forEach(([offset,color])=>radial.appendChild(el('stop',{offset,'stop-color':color})));d.appendChild(radial);
    });
    svg.appendChild(d);
  }
  function drawBoard(svg,scene){const {cols=8,rows=5,size=42,offsetX=66,offsetY=55}=scene.board||{};const g=el('g');for(let r=0;r<rows;r++)for(let q=0;q<cols;q++){const p=axial(q,r,size,offsetX,offsetY);g.appendChild(el('polygon',{points:hexPoints(p.x,p.y,size-2),fill:palette.cell,stroke:palette.cellLine,'stroke-width':1.1,opacity:.72}));}svg.appendChild(g);}
  function drawAtom(svg,item,scene,id){
    const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);
    const symbol=String(item.element||'Fe');
    const c=elements[symbol]||elements.Fe;
    const g=el('g',{transform:`translate(${p.x} ${p.y})`,'data-atom':symbol});
    const body=el('g',{filter:`url(#shadow-${id})`});
    body.appendChild(el('circle',{r:27,fill:'#090c0b',stroke:'#121817','stroke-width':2}));
    body.appendChild(el('circle',{r:24.5,fill:`url(#bevel-${id})`,stroke:'#3b372d','stroke-width':1.4}));
    body.appendChild(el('circle',{r:20.5,fill:c.dark,stroke:'#151815','stroke-width':1.5}));
    body.appendChild(el('circle',{r:18.2,fill:`url(#atom-${symbol}-${id})`,stroke:c.light,'stroke-width':1.3}));
    body.appendChild(el('circle',{r:14.6,fill:'none',stroke:c.dark,'stroke-width':1.5,opacity:.85}));
    body.appendChild(el('ellipse',{cx:-5,cy:-7,rx:8.2,ry:4.2,fill:'#fff',opacity:.18,transform:'rotate(-20)'}));
    for(let i=0;i<6;i++){const a=i*Math.PI/3;body.appendChild(el('circle',{cx:23.2*Math.cos(a),cy:23.2*Math.sin(a),r:1.5,fill:'#2e2b23',stroke:'#c8bb93','stroke-width':.7}));}
    g.appendChild(body);
    const t=el('text',{x:0,y:.5,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Georgia, Times New Roman, serif','font-size':17,'font-weight':700,'letter-spacing':'-.4px',fill:'#17130d',stroke:'#f0dfad','stroke-width':.9,'paint-order':'stroke fill','stroke-linejoin':'round','text-rendering':'geometricPrecision','pointer-events':'none'});
    t.textContent=symbol;
    g.appendChild(t);
    svg.appendChild(g);
  }
  function drawArm(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const angle=(item.rotation||0)*60;const len=(item.length||1)*scene.board.size*SQRT3;const g=el('g',{transform:`translate(${p.x} ${p.y}) rotate(${angle})`});g.appendChild(el('circle',{r:22,fill:palette.shadow,opacity:.5}));g.appendChild(el('circle',{r:18,fill:palette.brassDark,stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:6,fill:palette.brass}));g.appendChild(el('rect',{x:8,y:-6,width:len-16,height:12,rx:5,fill:palette.brass,stroke:palette.metal,'stroke-width':2}));g.appendChild(el('path',{d:`M${len-8},-10 L${len+8},0 L${len-8},10 Z`,fill:palette.metal,stroke:palette.brassDark,'stroke-width':2}));svg.appendChild(g);}
  function drawProjection(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:29,fill:palette.shadow,stroke:palette.brass,'stroke-width':5}));g.appendChild(el('circle',{r:21,fill:'none',stroke:palette.metal,'stroke-width':3}));g.appendChild(el('circle',{r:11,fill:'#8c236d',stroke:'#f0b7df','stroke-width':3}));for(let i=0;i<4;i++)g.appendChild(el('path',{d:'M0,-38 L6,-27 L-6,-27 Z',fill:palette.metal,transform:`rotate(${i*90})`}));svg.appendChild(g);}
  function drawBonding(svg,item,scene){const p=axial(item.q,item.r,scene.board.size,scene.board.offsetX,scene.board.offsetY);const g=el('g',{transform:`translate(${p.x} ${p.y})`});g.appendChild(el('circle',{r:28,fill:palette.shadow,stroke:palette.brass,'stroke-width':4}));g.appendChild(el('path',{d:'M-12,-9 L0,0 L12,-9 M-12,9 L0,0 L12,9',fill:'none',stroke:palette.metal,'stroke-width':4,'stroke-linecap':'round'}));svg.appendChild(g);}
  function drawTrack(svg,item,scene){const a=axial(item.q1,item.r1,scene.board.size,scene.board.offsetX,scene.board.offsetY);const b=axial(item.q2,item.r2,scene.board.size,scene.board.offsetX,scene.board.offsetY);svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.brassDark,'stroke-width':12,'stroke-linecap':'round'}));svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:palette.metal,'stroke-width':3,'stroke-dasharray':'8 8','stroke-linecap':'round'}));}
  function render(scene){const width=scene.width||720,height=scene.height||360;const id=++renderId;scene.board={cols:8,rows:5,size:42,offsetX:66,offsetY:55,...scene.board};const svg=el('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':scene.label||'Opus Magnum scene'});defs(svg,id);svg.appendChild(el('rect',{width,height,fill:palette.board}));drawBoard(svg,scene);(scene.tracks||[]).forEach(x=>drawTrack(svg,x,scene));(scene.glyphs||[]).forEach(x=>x.type==='projection'?drawProjection(svg,x,scene):x.type==='bonding'?drawBonding(svg,x,scene):null);(scene.arms||[]).forEach(x=>drawArm(svg,x,scene));(scene.atoms||[]).forEach(x=>drawAtom(svg,x,scene,id));return svg.outerHTML;}
  window.OpusJS={version:'0.2.1',render,axial};
})();