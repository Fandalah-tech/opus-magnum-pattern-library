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

  function applyArm(group, part) {
    const core = window.OpusRendererCore;
    if (!core || !group || !part) return;
    const offsets = core.branchOffsets(part.type);
    group.dataset.branchCount = String(offsets.length);
    if (offsets.length <= 1) return;

    const shadowTemplate = group.querySelector('[data-arm-shadow="0"]');
    const shaftTemplate = group.querySelector('[data-arm-shaft="0"]');
    const tipTemplate = group.querySelector('[data-arm-tip="0"]');
    const gripTemplate = group.querySelector('[data-arm-grip="0"]');
    const insertionPoint = group.querySelector('.viewer-arm-base-shadow');
    if (!shadowTemplate || !shaftTemplate || !tipTemplate || !gripTemplate) return;

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

  function apply(viewer, solution) {
    const root = viewer?.root || document.querySelector('#solution-viewer');
    if (!root) return;
    for (const part of solution?.parts || []) {
      if (!/^(arm[1236]|baron)$/.test(String(part.type || ''))) continue;
      const group = root.querySelector(`[data-part-id="${CSS.escape(String(part.id))}"]`);
      applyArm(group, part);
    }
  }

  window.OpusStaticArmFidelity = Object.freeze({ apply, applyArm });
})();
