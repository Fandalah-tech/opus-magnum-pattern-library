(() => {
  if (!window.OpusJS?.render) return;

  const originalRender = window.OpusJS.render;
  const NS = 'http://www.w3.org/2000/svg';

  function parseTransform(transform = '') {
    const match = transform.match(/translate\(([-\d.]+)[ ,]([-\d.]+)\)\s*rotate\(([-\d.]+)\)/);
    return match ? { x: Number(match[1]), y: Number(match[2]), angle: Number(match[3]) } : null;
  }

  function directChildren(node, selector) {
    return [...node.children].filter(child => child.matches(selector));
  }

  function buildSharedHub(svg, arms, origin) {
    const firstArm = arms[0];
    const firstBody = firstArm.firstElementChild;
    if (!firstBody) return;

    const base = firstBody.querySelector(':scope > g[data-base="masterHexBaseV1"]');
    const hubCircles = directChildren(firstBody, 'circle').filter(circle => {
      const cx = Number(circle.getAttribute('cx') || 0);
      const cy = Number(circle.getAttribute('cy') || 0);
      return Math.abs(cx) < 0.01 && Math.abs(cy) < 0.01;
    }).slice(0, 4);

    if (!base || hubCircles.length < 4) return;

    const shared = document.createElementNS(NS, 'g');
    shared.setAttribute('transform', `translate(${origin.x} ${origin.y})`);
    shared.setAttribute('data-arm-group', String(arms.length));
    shared.appendChild(base.cloneNode(true));

    arms.forEach(arm => {
      const body = arm.firstElementChild;
      body?.querySelector(':scope > g[data-base="masterHexBaseV1"]')?.remove();

      directChildren(body, 'circle').filter(circle => {
        const cx = Number(circle.getAttribute('cx') || 0);
        const cy = Number(circle.getAttribute('cy') || 0);
        return Math.abs(cx) < 0.01 && Math.abs(cy) < 0.01;
      }).slice(0, 4).forEach(circle => circle.remove());

      directChildren(body, 'g').filter(group => group.querySelector(':scope > text')).forEach(group => group.remove());
    });

    const collarLayer = document.createElementNS(NS, 'g');
    collarLayer.setAttribute('data-arm-collars', 'true');
    arms.forEach(arm => {
      const parsed = parseTransform(arm.getAttribute('transform'));
      if (!parsed) return;
      const angle = parsed.angle * Math.PI / 180;
      const cx = Math.cos(angle) * 20.2;
      const cy = Math.sin(angle) * 20.2;

      const outer = document.createElementNS(NS, 'circle');
      outer.setAttribute('cx', cx);
      outer.setAttribute('cy', cy);
      outer.setAttribute('r', '5.2');
      outer.setAttribute('fill', '#34393d');
      outer.setAttribute('stroke', '#202427');
      outer.setAttribute('stroke-width', '1.15');
      collarLayer.appendChild(outer);

      const inner = document.createElementNS(NS, 'circle');
      inner.setAttribute('cx', cx);
      inner.setAttribute('cy', cy);
      inner.setAttribute('r', '3.65');
      inner.setAttribute('fill', '#b9bec0');
      inner.setAttribute('stroke', '#f0f1ef');
      inner.setAttribute('stroke-width', '.55');
      collarLayer.appendChild(inner);

      const rivet = document.createElementNS(NS, 'circle');
      rivet.setAttribute('cx', cx);
      rivet.setAttribute('cy', cy);
      rivet.setAttribute('r', '1.25');
      rivet.setAttribute('fill', '#850d64');
      rivet.setAttribute('stroke', '#3b102f');
      rivet.setAttribute('stroke-width', '.45');
      collarLayer.appendChild(rivet);
    });
    shared.appendChild(collarLayer);

    hubCircles.forEach(circle => shared.appendChild(circle.cloneNode(true)));

    const lengths = arms.map(arm => Number(arm.dataset.length || 1));
    const labelValue = lengths.every(length => length === lengths[0]) ? lengths[0] : Math.min(...lengths);
    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', '0');
    label.setAttribute('y', '.7');
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('dominant-baseline', 'middle');
    label.setAttribute('font-family', 'Georgia, Times New Roman, serif');
    label.setAttribute('font-size', '17.5');
    label.setAttribute('font-weight', '700');
    label.setAttribute('fill', '#fffdf4');
    label.setAttribute('stroke', '#251f27');
    label.setAttribute('stroke-width', '.5');
    label.setAttribute('paint-order', 'stroke');
    label.textContent = String(labelValue);
    shared.appendChild(label);

    const firstAtom = svg.querySelector('g[data-atom]');
    svg.insertBefore(shared, firstAtom || null);
  }

  function normalizeMultiArms(svg) {
    const groups = new Map();
    svg.querySelectorAll('g[data-arm="simple"]').forEach(arm => {
      const parsed = parseTransform(arm.getAttribute('transform'));
      if (!parsed) return;
      const key = `${parsed.x.toFixed(3)},${parsed.y.toFixed(3)}`;
      if (!groups.has(key)) groups.set(key, { origin: parsed, arms: [] });
      groups.get(key).arms.push(arm);
    });

    groups.forEach(({ origin, arms }) => {
      if (arms.length > 1) buildSharedHub(svg, arms, origin);
    });
  }

  window.OpusJS.render = scene => {
    const markup = originalRender(scene);
    const documentNode = new DOMParser().parseFromString(markup, 'image/svg+xml');
    const svg = documentNode.documentElement;
    normalizeMultiArms(svg);
    return new XMLSerializer().serializeToString(svg);
  };

  window.OpusJS.version = '1.5.0';
})();
