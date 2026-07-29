(() => {
  if (!window.OpusJS?.render) return;

  const originalRender = window.OpusJS.render;
  const NS = 'http://www.w3.org/2000/svg';
  const SQRT3 = Math.sqrt(3);
  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  const axial = (q, r, size, ox, oy) => ({
    x: ox + size * SQRT3 * (q + r / 2),
    y: oy + size * 1.5 * r
  });
  const directions = [{q:1,r:0},{q:0,r:1},{q:-1,r:1},{q:-1,r:0},{q:0,r:-1},{q:1,r:-1}];
  const hexPoints = size => Array.from({length:6}, (_, i) => {
    const angle = Math.PI / 180 * (60 * i - 30);
    return `${size * Math.cos(angle)},${size * Math.sin(angle)}`;
  }).join(' ');

  function addDefs(svg, id) {
    const defs = svg.querySelector('defs') || svg.insertBefore(svgEl('defs'), svg.firstChild);
    const silver = svgEl('linearGradient', {id:`piston-silver-${id}`,x1:'0%',y1:'0%',x2:'0%',y2:'100%'});
    [['0%','#f5f6f5'],['22%','#d4d7d6'],['50%','#777e81'],['78%','#c8cccc'],['100%','#484e52']]
      .forEach(([offset,color]) => silver.appendChild(svgEl('stop',{offset,'stop-color':color})));
    defs.appendChild(silver);
    const dial = svgEl('radialGradient', {id:`piston-dial-${id}`,cx:'42%',cy:'30%',r:'72%'});
    [['0%','#d45ed8'],['36%','#8b2794'],['72%','#4d1056'],['100%','#210428']]
      .forEach(([offset,color]) => dial.appendChild(svgEl('stop',{offset,'stop-color':color})));
    defs.appendChild(dial);
  }

  function drawPiston(svg, item, scene, id) {
    const board = {size:42,offsetX:66,offsetY:55,...(scene.board || {})};
    const rotation = ((Number(item.rotation) || 0) % 6 + 6) % 6;
    const length = Math.max(1, Math.min(3, Number(item.length) || 1));
    const origin = axial(item.q, item.r, board.size, board.offsetX, board.offsetY);
    const direction = directions[rotation];
    const target = axial(item.q + direction.q * length, item.r + direction.r * length, board.size, board.offsetX, board.offsetY);
    const dx = target.x - origin.x;
    const dy = target.y - origin.y;
    const distance = Math.hypot(dx, dy);
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;
    const group = svgEl('g', {transform:`translate(${origin.x} ${origin.y})`,'data-piston-arm':'masterPistonV1'});

    group.appendChild(svgEl('polygon',{points:hexPoints(board.size-2),fill:'#101514',stroke:'#8a6940','stroke-width':1.35}));
    group.appendChild(svgEl('polygon',{points:hexPoints(board.size-5.2),fill:'#171d1b',stroke:'#050706','stroke-width':.9}));

    const arm = svgEl('g',{transform:`rotate(${angle})`});
    arm.appendChild(svgEl('rect',{x:17,y:-8.2,width:distance-35,height:16.4,rx:8.2,fill:'#202527',stroke:'#090c0b','stroke-width':2}));
    arm.appendChild(svgEl('rect',{x:20,y:-5.4,width:distance-42,height:10.8,rx:5.4,fill:`url(#piston-silver-${id})`,stroke:'#eef0ef','stroke-width':.65}));
    arm.appendChild(svgEl('rect',{x:30,y:-2.75,width:distance-53,height:5.5,rx:2.75,fill:'#2e3436',stroke:'#171b1c','stroke-width':.8}));
    for (let i=1;i<length;i++) {
      const x = distance * i / length;
      arm.appendChild(svgEl('circle',{cx:x,cy:0,r:6.1,fill:'#252a2d',stroke:'#0d1011','stroke-width':1}));
      arm.appendChild(svgEl('circle',{cx:x,cy:0,r:3.9,fill:`url(#piston-silver-${id})`,stroke:'#f0f1ef','stroke-width':.45}));
    }

    const gripX = distance;
    arm.appendChild(svgEl('circle',{cx:gripX,cy:0,r:25.8,fill:'none',stroke:'#34393d','stroke-width':4.1}));
    arm.appendChild(svgEl('circle',{cx:gripX,cy:0,r:25.8,fill:'none',stroke:`url(#piston-silver-${id})`,'stroke-width':2.55}));
    [0,120,240].forEach(deg=>{
      const rad=deg*Math.PI/180;
      arm.appendChild(svgEl('line',{x1:gripX+Math.cos(rad)*26.4,y1:Math.sin(rad)*26.4,x2:gripX+Math.cos(rad)*33.4,y2:Math.sin(rad)*33.4,stroke:`url(#piston-silver-${id})`,'stroke-width':3.2,'stroke-linecap':'round'}));
    });
    const jawStart=gripX-24.6;
    arm.appendChild(svgEl('path',{d:`M${jawStart},-5.8 C${jawStart+5.2},-13.4 ${gripX-11.5},-26.9 ${gripX+.4},-26.05 A26.05,26.05 0 0 0 ${jawStart},5.8`,fill:'none',stroke:`url(#piston-silver-${id})`,'stroke-width':4.1,'stroke-linecap':'round'}));
    arm.appendChild(svgEl('circle',{cx:jawStart+1.35,cy:-7.15,r:1.65,fill:'#850d64',stroke:'#3b102f','stroke-width':.6}));
    group.appendChild(arm);

    group.appendChild(svgEl('circle',{r:23.2,fill:`url(#piston-silver-${id})`,stroke:'#3d4347','stroke-width':1.15}));
    group.appendChild(svgEl('circle',{r:18.7,fill:'#d7c68a',stroke:'#766842','stroke-width':1}));
    group.appendChild(svgEl('circle',{r:14.8,fill:`url(#piston-dial-${id})`,stroke:'#310538','stroke-width':1.2}));
    const label = svgEl('text',{x:0,y:.7,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Georgia, Times New Roman, serif','font-size':16.5,'font-weight':700,fill:'#fffdf4',stroke:'#251f27','stroke-width':.5,'paint-order':'stroke'});
    label.textContent='P';
    group.appendChild(label);

    const firstAtom = svg.querySelector('g[data-atom]');
    svg.insertBefore(group, firstAtom || null);
  }

  window.OpusJS.render = scene => {
    const pistons = (scene.arms || []).filter(arm => arm.type === 'piston');
    const cleanScene = {...scene, arms:(scene.arms || []).filter(arm => arm.type !== 'piston')};
    const markup = originalRender(cleanScene);
    if (!pistons.length) return markup;
    const doc = new DOMParser().parseFromString(markup,'image/svg+xml');
    const svg = doc.documentElement;
    const id = `piston-${Date.now().toString(36)}`;
    addDefs(svg,id);
    pistons.forEach(item=>drawPiston(svg,item,scene,id));
    return new XMLSerializer().serializeToString(svg);
  };

  const currentVersion = String(window.OpusJS.version || '0.0.0');
  if (currentVersion.localeCompare('1.8.1', undefined, { numeric: true }) < 0) window.OpusJS.version = '1.8.1';

  if (window.OpusAssetGallery?.entries) {
    const existing = window.OpusAssetGallery.entries.find(entry => entry.id === 'arm-piston');
    const pistonEntry = {
      id:'arm-piston',group:'Mechanisms',name:'Piston arm',status:'draft',reference:'parts',calibratable:false,
      notes:['Temporary V1 restored for comparison','Canonical telescoping geometry still requires reconstruction'],
      scene:{width:420,height:250,board:{cols:5,rows:3,size:38,offsetX:62,offsetY:58},arms:[{type:'piston',q:0,r:1,length:3,rotation:0}]}
    };
    if (existing) Object.assign(existing, pistonEntry);
    else window.OpusAssetGallery.entries.splice(10,0,pistonEntry);
  }
})();