(() => {
  if (!window.OpusJS?.render) return;
  const originalRender = window.OpusJS.render;
  const NS = 'http://www.w3.org/2000/svg';
  const VALID_COUNTS = new Set([2, 3, 6]);

  const parseTransform = (transform = '') => {
    const match = transform.match(/translate\(([-\d.]+)[ ,]([-\d.]+)\)\s*rotate\(([-\d.]+)\)/);
    return match ? { x:Number(match[1]), y:Number(match[2]), angle:Number(match[3]) } : null;
  };
  const directChildren = (node, selector) => [...node.children].filter(child => child.matches(selector));
  const canonicalAngle = angle => ((Math.round(angle / 60) * 60) % 360 + 360) % 360;

  function buildSharedHub(svg, arms, origin) {
    const unique = new Map();
    arms.forEach(arm => {
      const parsed = parseTransform(arm.getAttribute('transform'));
      if (!parsed) return;
      const angle = canonicalAngle(parsed.angle);
      if (!unique.has(angle)) unique.set(angle, arm);
    });
    arms = [...unique.values()];
    if (!VALID_COUNTS.has(arms.length)) return;

    const firstBody = arms[0].firstElementChild;
    if (!firstBody) return;
    const base = firstBody.querySelector(':scope > g[data-base="masterHexBaseV1"]');
    const hubCircles = directChildren(firstBody, 'circle').filter(circle => {
      const cx = Number(circle.getAttribute('cx') || 0), cy = Number(circle.getAttribute('cy') || 0);
      return Math.abs(cx) < .01 && Math.abs(cy) < .01;
    }).slice(0,4);
    if (!base || hubCircles.length < 4) return;

    arms.forEach(arm => {
      const body = arm.firstElementChild;
      body?.querySelector(':scope > g[data-base="masterHexBaseV1"]')?.remove();
      directChildren(body,'circle').filter(circle => {
        const cx = Number(circle.getAttribute('cx') || 0), cy = Number(circle.getAttribute('cy') || 0);
        return Math.abs(cx) < .01 && Math.abs(cy) < .01;
      }).slice(0,4).forEach(circle => circle.remove());
      directChildren(body,'g').filter(group => group.querySelector(':scope > text')).forEach(group => group.remove());
    });

    const shared = document.createElementNS(NS,'g');
    shared.setAttribute('transform',`translate(${origin.x} ${origin.y})`);
    shared.setAttribute('data-arm-group',String(arms.length));
    shared.appendChild(base.cloneNode(true));

    const collars = document.createElementNS(NS,'g');
    collars.setAttribute('data-arm-collars','true');
    arms.forEach(arm => {
      const parsed = parseTransform(arm.getAttribute('transform'));
      const rad = canonicalAngle(parsed.angle) * Math.PI / 180;
      const cx = Math.cos(rad) * 20.4, cy = Math.sin(rad) * 20.4;
      const parts = [
        ['circle',{cx,cy,r:5.5,fill:'#34393d',stroke:'#202427','stroke-width':1.2}],
        ['circle',{cx,cy,r:3.9,fill:'#b9bec0',stroke:'#f0f1ef','stroke-width':.58}],
        ['circle',{cx,cy,r:1.3,fill:'#850d64',stroke:'#3b102f','stroke-width':.45}]
      ];
      parts.forEach(([name,attrs])=>{const node=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));collars.appendChild(node);});
    });
    shared.appendChild(collars);
    hubCircles.forEach(circle => shared.appendChild(circle.cloneNode(true)));

    const lengths = arms.map(arm => Number(arm.dataset.length || 1));
    const label = document.createElementNS(NS,'text');
    Object.entries({x:0,y:.7,'text-anchor':'middle','dominant-baseline':'middle','font-family':'Georgia, Times New Roman, serif','font-size':17.5,'font-weight':700,fill:'#fffdf4',stroke:'#251f27','stroke-width':.5,'paint-order':'stroke'}).forEach(([k,v])=>label.setAttribute(k,v));
    label.textContent = String(lengths.every(n=>n===lengths[0]) ? lengths[0] : Math.min(...lengths));
    shared.appendChild(label);

    const firstAtom = svg.querySelector('g[data-atom]');
    svg.insertBefore(shared, firstAtom || null);
  }

  function normalize(svg) {
    const groups = new Map();
    svg.querySelectorAll('g[data-arm="simple"]').forEach(arm => {
      const parsed = parseTransform(arm.getAttribute('transform'));
      if (!parsed) return;
      const key = `${parsed.x.toFixed(3)},${parsed.y.toFixed(3)}`;
      if (!groups.has(key)) groups.set(key,{origin:parsed,arms:[]});
      groups.get(key).arms.push(arm);
    });
    groups.forEach(({origin,arms}) => buildSharedHub(svg,arms,origin));
  }

  window.OpusJS.render = scene => {
    const doc = new DOMParser().parseFromString(originalRender(scene),'image/svg+xml');
    normalize(doc.documentElement);
    return new XMLSerializer().serializeToString(doc.documentElement);
  };
  window.OpusJS.version = '1.5.1';
})();
