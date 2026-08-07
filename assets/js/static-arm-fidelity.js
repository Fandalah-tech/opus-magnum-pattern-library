(() => {
  if (window.OpusStaticArmFidelity) return;

  function setEndpoint(node, x, y, index, attribute) {
    if (!node) return null;
    const clone = node.cloneNode(true);
    if (clone.tagName.toLowerCase() === 'line') {
      clone.setAttribute('x2', String(x));
      clone.setAttribute('y2', String(y));
    } else {
      clone.setAttribute('cx', String(x));
      clone.setAttribute('cy', String(y));
    }
    clone.setAttribute(attribute, String(index));
    return clone;
  }

  function applyPistonGeometry(group, x1, y1, x2, y2) {
    if (!group) return;
    const core = window.OpusRendererCore;
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

  function applyArm(group, part) {
    const core = window.OpusRendererCore;
    if (!core || !group || !part) return;
    const offsets = core.branchOffsets(part.type);
    group.dataset.branchCount = String(offsets.length);

    if (offsets.length > 1) {
      const shadowTemplate = group.querySelector('[data-arm-shadow="0"]');
      const shaftTemplate = group.querySelector('[data-arm-shaft="0"]');
      const tipTemplate = group.querySelector('[data-arm-tip="0"]');
      const gripTemplate = group.querySelector('[data-arm-grip="0"]');
      const insertionPoint = group.querySelector('.viewer-arm-base-shadow');
      if (shadowTemplate && shaftTemplate && tipTemplate && gripTemplate) {
        const tips = core.armTips(part);
        for (let index = 1; index < tips.length; index += 1) {
          if (group.querySelector(`[data-arm-shaft="${index}"]`)) continue;
          const [x, y] = core.axialToPixel(tips[index].position);
          const nodes = [
            setEndpoint(shadowTemplate, x, y, index, 'data-arm-shadow'),
            setEndpoint(shaftTemplate, x, y, index, 'data-arm-shaft'),
            setEndpoint(tipTemplate, x, y, index, 'data-arm-tip'),
            setEndpoint(gripTemplate, x, y, index, 'data-arm-grip')
          ].filter(Boolean);
          for (const node of nodes) group.insertBefore(node, insertionPoint || null);
        }
      }
    }

    if (part.type === 'piston') {
      const shaft = group.querySelector('[data-arm-shaft="0"]');
      if (shaft) applyPistonGeometry(
        group,
        Number(shaft.getAttribute('x1')) || 0,
        Number(shaft.getAttribute('y1')) || 0,
        Number(shaft.getAttribute('x2')) || 0,
        Number(shaft.getAttribute('y2')) || 0
      );
    }
  }

  function apply(viewer, solution) {
    const root = viewer?.root || document.querySelector('#solution-viewer');
    if (!root) return;
    for (const part of solution?.parts || []) {
      if (!/^(arm[1236]|baron|piston)$/.test(String(part.type || ''))) continue;
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      applyArm(group, part);
    }
  }

  window.OpusStaticArmFidelity = Object.freeze({ apply, applyArm, applyPistonGeometry });
})();
