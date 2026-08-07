(() => {
  if (window.OpusRendererCore) return;
  const NS = 'http://www.w3.org/2000/svg';
  const HEX_SIZE = 34;
  const SQRT3 = Math.sqrt(3);
  const DIRECTIONS = [[1,0],[0,1],[-1,1],[-1,0],[0,-1],[1,-1]];
  const ELEMENT_COLORS = {
    salt:'#f0eee5',air:'#9ed9e8',earth:'#8f7149',fire:'#e66c4d',water:'#5ea9d6',
    quicksilver:'#b9c0c9',gold:'#d8ae45',silver:'#c4ccd4',copper:'#b87445',iron:'#777b80',
    tin:'#aeb3b4',lead:'#6f6578',vitae:'#f0d46a',mors:'#a48bb9',quintessence:'#e8c2ff',repeat:'#d7d7d7'
  };
  const normalizeRotation = rotation => ((Number(rotation)||0)%6+6)%6;
  const axialToPixel = ([q=0,r=0]) => [HEX_SIZE * SQRT3 * (q + r / 2), -HEX_SIZE * 1.5 * r];
  const direction = rotation => DIRECTIONS[normalizeRotation(rotation)];
  const hexPoints = (x, y, radius = HEX_SIZE * .9) => Array.from({ length: 6 }, (_, i) => {
    const angle = Math.PI / 180 * (60 * i - 30);
    return `${x + radius * Math.cos(angle)},${y + radius * Math.sin(angle)}`;
  }).join(' ');
  const partKind = (type='') => {
    if (/^(arm|piston|baron)/.test(type)) return 'arm';
    if (type === 'input') return 'input';
    if (type.startsWith('out-')) return 'output';
    if (type === 'track') return 'track';
    if (type === 'conduit') return 'conduit';
    if (type.startsWith('glyph-') || type === 'bonder' || type === 'unbonder') return 'glyph';
    return 'part';
  };
  const boundsForHexes = (hexes=[]) => {
    if (!hexes.length) return null;
    const points = hexes.map(axialToPixel);
    const xs = points.map(([x]) => x), ys = points.map(([,y]) => y);
    return {minX:Math.min(...xs),maxX:Math.max(...xs),minY:Math.min(...ys),maxY:Math.max(...ys)};
  };
  const armGeometry = state => {
    const origin = state?.origin || [0,0];
    const [dq,dr] = direction(state?.rotation);
    const length = Math.max(1, Number(state?.length || 1));
    const tip = [origin[0] + dq * length, origin[1] + dr * length];
    const [x1,y1] = axialToPixel(origin), [x2,y2] = axialToPixel(tip);
    return {origin,tip,x1,y1,x2,y2};
  };
  const svgEl = (name, attrs={}) => {
    const node = document.createElementNS(NS,name);
    for (const [key,value] of Object.entries(attrs)) if (value !== undefined && value !== null) node.setAttribute(key,String(value));
    return node;
  };
  const interpolateHex = (start,end,t) => {
    const [sx,sy] = axialToPixel(start || end || [0,0]);
    const [ex,ey] = axialToPixel(end || start || [0,0]);
    return [sx + (ex-sx)*t, sy + (ey-sy)*t];
  };
  const easeOutCubic = t => 1 - Math.pow(1 - Math.max(0,Math.min(1,t)),3);
  window.OpusRendererCore = Object.freeze({NS,HEX_SIZE,SQRT3,DIRECTIONS,ELEMENT_COLORS,normalizeRotation,axialToPixel,direction,hexPoints,partKind,boundsForHexes,armGeometry,svgEl,interpolateHex,easeOutCubic});
})();
