(() => {
  if (window.OpusStaticArmFidelity) return;

  function applyPistonGeometry(group, x1, y1, x2, y2) {
    const core = window.OpusRendererCore;
    if (!core || !group) return;
    const mix = (a, b, t) => a + (b - a) * t;
    let sleeve = group.querySelector('[data-piston-sleeve]');
    let rod = group.querySelector('[data-piston-rod]');
    const insertionPoint = group.querySelector('.viewer-arm-base-shadow');
    if (!sleeve) {
      sleeve = core.svgEl('line', {
        'data-piston-sleeve': 'true',
        stroke: '#21170f',
        'stroke-width': 15,
        'stroke-linecap': 'round',
        class: 'viewer-piston-sleeve'
      });
      group.insertBefore(sleeve, insertionPoint || null);
    }
    if (!rod) {
      rod = core.svgEl('line', {
        'data-piston-rod': 'true',
        stroke: '#d4a457',
        'stroke-width': 5,
        'stroke-linecap': 'round',
        class: 'viewer-piston-rod'
      });
      group.insertBefore(rod, insertionPoint || null);
    }
    sleeve.setAttribute('x1', String(mix(x1, x2, .08)));
    sleeve.setAttribute('y1', String(mix(y1, y2, .08)));
    sleeve.setAttribute('x2', String(mix(x1, x2, .58)));
    sleeve.setAttribute('y2', String(mix(y1, y2, .58)));
    rod.setAttribute('x1', String(mix(x1, x2, .18)));
    rod.setAttribute('y1', String(mix(y1, y2, .18)));
    rod.setAttribute('x2', String(mix(x1, x2, .66)));
    rod.setAttribute('y2', String(mix(y1, y2, .66)));
    group.classList.add('viewer-piston');
  }

  function applyPiston(group) {
    if (!group) return;
    const shaft = group.querySelector('[data-arm-shaft="0"]');
    if (!shaft) return;
    applyPistonGeometry(
      group,
      Number(shaft.getAttribute('x1')) || 0,
      Number(shaft.getAttribute('y1')) || 0,
      Number(shaft.getAttribute('x2')) || 0,
      Number(shaft.getAttribute('y2')) || 0
    );
  }

  function apply(viewer, solution) {
    const root = viewer?.root || document.querySelector('#solution-viewer');
    if (!root) return;
    for (const part of solution?.parts || []) {
      if (part.type !== 'piston') continue;
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      applyPiston(group);
    }
  }

  window.OpusStaticArmFidelity = Object.freeze({ apply, applyPiston, applyPistonGeometry });
})();
