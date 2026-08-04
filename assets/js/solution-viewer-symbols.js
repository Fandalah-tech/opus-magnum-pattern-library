(() => {
  const base = window.OpusSolutionViewer;
  if (!base || !window.OpusGeometry || !window.OpusPieceSymbols) return;
  const SQRT3 = Math.sqrt(3), SIZE = 34;
  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };
  const palette = { input: "#74b9a5", output: "#d97b68", glyph: "#b397cc" };

  window.OpusSolutionViewer = {
    create(root) {
      const viewer = base.create(root);
      const nativeSelect = viewer.selectPart.bind(viewer);

      viewer.drawStation = function drawStation(group, part, kind) {
        const cells = window.OpusGeometry.occupiedCells(part);
        const centers = cells.map(axialToPixel);
        const color = palette[kind] || palette.glyph;
        const outline = svgEl("g", { class: "viewer-piece-footprint" });
        for (const [x, y] of centers) {
          const points = Array.from({ length: 6 }, (_, i) => {
            const angle = Math.PI / 180 * (60 * i - 30);
            return `${x + SIZE * .72 * Math.cos(angle)},${y + SIZE * .72 * Math.sin(angle)}`;
          }).join(" ");
          outline.append(svgEl("polygon", { points, fill: color, "fill-opacity": .11, stroke: color, "stroke-opacity": .7, "stroke-width": 2 }));
        }
        group.append(outline);
        window.OpusPieceSymbols.draw(group, part, centers, color, window.OpusGeometry.label(part.type));
      };

      viewer.selectPart = function selectPart(id) {
        nativeSelect(id);
        const related = new Set();
        for (const edge of this.graph?.edges || []) {
          if (edge.source === id) related.add(edge.target);
          if (edge.target === id) related.add(edge.source);
        }
        this.world.querySelectorAll("[data-part-id]").forEach((node) => {
          node.classList.toggle("related", related.has(node.dataset.partId));
          node.classList.toggle("dimmed", node.dataset.partId !== id && !related.has(node.dataset.partId));
        });
      };
      return viewer;
    }
  };
})();