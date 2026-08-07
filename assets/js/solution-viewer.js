(() => {
  const core = window.OpusRendererCore;
  const Scene = window.OpusScene;
  const SvgRenderer = window.OpusSvgRenderer;
  if (!core || !Scene || !SvgRenderer) throw new Error("OpusRendererCore, OpusScene and OpusSvgRenderer must load before solution-viewer.js");
  const SIZE = core.HEX_SIZE;
  const SQRT3 = core.SQRT3;
  const GEO = window.OpusGeometry;
  const axialToPixel = core.axialToPixel;
  const hexPoints = core.hexPoints;
  const svgEl = core.svgEl;
  const COLORS = SvgRenderer.COLORS;

  const escapeHtml = (value) => String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
  const formatPosition = (position) => Array.isArray(position) ? `(${position.join(", ")})` : "—";

  class SolutionViewer {
    constructor(root) {
      this.root = root;
      this.svg = root.querySelector("svg");
      this.world = root.querySelector("[data-viewer-world]");
      this.details = root.querySelector("[data-viewer-details]");
      this.zoomLabel = root.querySelector("[data-viewer-zoom]");
      this.scale = 1;
      this.tx = 0;
      this.ty = 0;
      this.drag = null;
      this.parts = [];
      this.graph = null;
      this.puzzle = null;
      this.replay = null;
      this.scene = null;
      this.selectedId = null;
      this.renderer = SvgRenderer.create(this.world, {
        onPartActivate: (partId) => this.selectPart(partId)
      });
      this.bind();
    }

    bind() {
      this.root.querySelector("[data-viewer-fit]")?.addEventListener("click", () => this.fit());
      this.root.querySelector("[data-viewer-reset]")?.addEventListener("click", () => {
        this.scale = 1;
        this.tx = 0;
        this.ty = 0;
        this.applyTransform();
      });
      this.svg.addEventListener("wheel", (event) => {
        event.preventDefault();
        const rect = this.svg.getBoundingClientRect();
        const pointerX = event.clientX - rect.left;
        const pointerY = event.clientY - rect.top;
        const worldX = (pointerX - this.tx) / this.scale;
        const worldY = (pointerY - this.ty) / this.scale;
        const nextScale = Math.max(.25, Math.min(4, this.scale * (event.deltaY < 0 ? 1.12 : .89)));
        this.tx = pointerX - worldX * nextScale;
        this.ty = pointerY - worldY * nextScale;
        this.scale = nextScale;
        this.applyTransform();
      }, { passive: false });
      this.svg.addEventListener("pointerdown", (event) => {
        if (event.target.closest("[data-part-id], [data-atom-id], [data-molecule-id]")) return;
        this.drag = { x: event.clientX, y: event.clientY, tx: this.tx, ty: this.ty };
        this.svg.setPointerCapture(event.pointerId);
      });
      this.svg.addEventListener("pointermove", (event) => {
        if (!this.drag) return;
        this.tx = this.drag.tx + event.clientX - this.drag.x;
        this.ty = this.drag.ty + event.clientY - this.drag.y;
        this.applyTransform();
      });
      this.svg.addEventListener("pointerup", () => { this.drag = null; });
      this.svg.addEventListener("pointercancel", () => { this.drag = null; });
      this.root.addEventListener("opus:viewerselect", (event) => this.selectReplayObject(event.detail));
    }

    layer(name) {
      return this.renderer.layer(name);
    }

    render(solution, graph, puzzle = null, replay = null) {
      const scene = Scene.build({ solution, graph, puzzle, replay });
      return this.renderScene(scene);
    }

    renderScene(scene) {
      if (!scene?.static) throw new Error("SolutionViewer.renderScene requires an Opus scene");
      this.scene = scene;
      this.parts = scene.static.parts || [];
      this.graph = scene.source.graph || null;
      this.puzzle = scene.source.puzzle || null;
      this.replay = scene.source.replay || null;
      this.selectedId = null;
      this.renderer.render(scene);
      if (!this.parts.length) {
        if (this.details) this.details.innerHTML = '<p class="hint">No parts in this solution.</p>';
        return this;
      }
      this.fit();
      this.selectPart(this.parts[0]?.id);
      return this;
    }

    relationSet(id) {
      return Scene.related(this.scene, id);
    }

    selectPart(id) {
      this.selectedId = id;
      const related = this.relationSet(id);
      this.world.querySelectorAll("[data-part-id]").forEach((node) => {
        const isSelected = node.dataset.partId === id;
        const isRelated = related.has(node.dataset.partId);
        node.classList.toggle("selected", isSelected);
        node.classList.toggle("related", isRelated);
        node.classList.toggle("dimmed", !isSelected && !isRelated);
      });
      const part = this.parts.find((item) => item.id === id);
      if (!part) return;
      this.renderSelectionOverlay(part, related);
      this.renderPartInspector(part, related);
    }

    selectReplayObject(detail = {}) {
      if (!detail || !this.details) return;
      this.world.querySelectorAll("[data-part-id]").forEach((node) => node.classList.remove("selected", "related", "dimmed"));
      this.layer("overlay").replaceChildren();
      if (detail.kind === "atom") this.renderAtomInspector(detail.atom, detail.molecule);
      else if (detail.kind === "molecule") this.renderMoleculeInspector(detail.molecule);
    }

    renderSelectionOverlay(part, related) {
      const overlay = this.layer("overlay");
      overlay.replaceChildren();
      for (const cell of part.occupiedCells || GEO.occupiedCells(part)) {
        const [x, y] = axialToPixel(cell);
        overlay.append(svgEl("polygon", {
          points: hexPoints(x, y, SIZE * .84),
          fill: COLORS.selected,
          "fill-opacity": .08,
          stroke: COLORS.selected,
          "stroke-width": 2.8,
          "stroke-dasharray": "5 5",
          class: "viewer-selection-cell"
        }));
      }
      for (const relationId of related) {
        const relatedPart = this.parts.find((item) => item.id === relationId);
        if (!relatedPart) continue;
        const [x, y] = axialToPixel(relatedPart.position || [0, 0]);
        overlay.append(svgEl("circle", {
          cx: x, cy: y, r: SIZE * .48,
          fill: "none", stroke: COLORS.related, "stroke-width": 1.8, "stroke-opacity": .72,
          class: "viewer-related-marker"
        }));
      }
    }

    commonRows(part) {
      return [
        ["Type", part.type],
        ["ID", part.id],
        ["Position", formatPosition(part.position)],
        ["Rotation", part.rotation ?? 0]
      ];
    }

    partRows(part, kind, related) {
      const footprint = part.occupiedCells || GEO.occupiedCells(part);
      const rows = this.commonRows(part);
      if (kind === "arm") {
        rows.push(
          ["Length", part.length ?? 1],
          ["Arm number", part.armNumber ?? "—"],
          ["Branches", part.armTips?.length || core.branchOffsets(part.type).length],
          ["Instructions", (part.program || []).length]
        );
      } else if (kind === "input") {
        const reagent = this.puzzle?.reagents?.[Number(part.which || 0)];
        rows.push(
          ["Reagent slot", Number(part.which || 0) + 1],
          ["Reagent atoms", reagent?.atoms?.length ?? "—"],
          ["Spawn footprint", footprint.length]
        );
      } else if (kind === "output") {
        const product = this.puzzle?.products?.[Number(part.which || 0)];
        rows.push(
          ["Output mode", part.type === "out-rep" ? "Repeating" : "Standard"],
          ["Product slot", Number(part.which || 0) + 1],
          ["Expected atoms", product?.atoms?.filter((atom) => atom.element !== "repeat").length ?? "—"]
        );
      } else if (kind === "track") {
        rows.push(
          ["Track cells", footprint.length],
          ["Path", footprint.map(formatPosition).join(" → ")]
        );
      } else if (kind === "conduit") {
        rows.push(
          ["Conduit ID", part.conduitId ?? part.id],
          ["Cells", footprint.length]
        );
      } else {
        rows.push(
          ["Glyph family", part.type.replace(/^glyph-/, "")],
          ["Footprint cells", footprint.length]
        );
      }
      rows.push(["Relations", related.size]);
      return rows;
    }

    renderPartInspector(part, related) {
      if (!this.details) return;
      const kind = part.kind || core.partKind(part.type);
      const program = kind === "arm" ? (part.program || []) : [];
      const rows = this.partRows(part, kind, related);
      const relatedRows = [...related].map((id) => {
        const item = this.parts.find((candidate) => candidate.id === id);
        return `<li><button type="button" data-inspect-part="${escapeHtml(id)}"><b>${escapeHtml(item?.type || "part")}</b><span>${escapeHtml(id)}</span></button></li>`;
      }).join("");
      this.details.innerHTML = `
        <header class="viewer-inspector-head">
          <span class="viewer-kind-badge ${escapeHtml(kind)}">${escapeHtml(kind)}</span>
          <div><h4>${escapeHtml(part.type)}</h4><p>${escapeHtml(part.id)}</p></div>
        </header>
        <section class="viewer-inspector-section">
          <h5>Properties</h5>
          <dl>${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>
        </section>
        ${program.length ? `<section class="viewer-inspector-section"><h5>Program</h5><ol class="viewer-program">${program.slice(0, 120).map((item) => `<li><b>${escapeHtml(item.cycle)}</b><span>${escapeHtml(item.instruction)}</span></li>`).join("")}</ol></section>` : ""}
        ${relatedRows ? `<section class="viewer-inspector-section"><h5>Related parts</h5><ul class="viewer-related-list">${relatedRows}</ul></section>` : ""}
      `;
      this.details.querySelectorAll("[data-inspect-part]").forEach((button) => {
        button.addEventListener("click", () => this.selectPart(button.dataset.inspectPart));
      });
    }

    renderAtomInspector(atom, molecule) {
      if (!atom || !this.details) return;
      const rows = [
        ["Element", atom.element],
        ["Atom ID", atom.id],
        ["Position", formatPosition(atom.position)],
        ["Molecule", molecule?.id || "—"],
        ["Held by", Array.isArray(molecule?.heldBy) && molecule.heldBy.length ? molecule.heldBy.join(", ") : "None"]
      ];
      this.details.innerHTML = `<header class="viewer-inspector-head"><span class="viewer-kind-badge atom">atom</span><div><h4>${escapeHtml(atom.element)}</h4><p>${escapeHtml(atom.id)}</p></div></header><section class="viewer-inspector-section"><h5>Properties</h5><dl>${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></section>`;
    }

    renderMoleculeInspector(molecule) {
      if (!molecule || !this.details) return;
      const rows = [
        ["Molecule ID", molecule.id],
        ["Atoms", molecule.atoms?.length ?? 0],
        ["Bonds", molecule.bonds?.length ?? 0],
        ["Held by", Array.isArray(molecule?.heldBy) && molecule.heldBy.length ? molecule.heldBy.join(", ") : "None"]
      ];
      const atoms = (molecule.atoms || []).map((atom) => `<li><b>${escapeHtml(atom.element)}</b><span>${escapeHtml(formatPosition(atom.position))}</span></li>`).join("");
      this.details.innerHTML = `<header class="viewer-inspector-head"><span class="viewer-kind-badge molecule">molecule</span><div><h4>Molecule</h4><p>${escapeHtml(molecule.id)}</p></div></header><section class="viewer-inspector-section"><h5>Properties</h5><dl>${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></section>${atoms ? `<section class="viewer-inspector-section"><h5>Atoms</h5><ul class="viewer-related-list">${atoms}</ul></section>` : ""}`;
    }

    kind(type = "") {
      return core.partKind(type);
    }

    applyTransform() {
      this.world.setAttribute("transform", `translate(${this.tx} ${this.ty}) scale(${this.scale})`);
      if (this.zoomLabel) this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    }

    fit() {
      const box = this.world.getBBox();
      const width = this.svg.clientWidth || 900;
      const height = this.svg.clientHeight || 560;
      if (!box.width || !box.height) return;
      this.scale = Math.max(.25, Math.min(2.4, Math.min((width - 96) / box.width, (height - 96) / box.height)));
      this.tx = width / 2 - (box.x + box.width / 2) * this.scale;
      this.ty = height / 2 - (box.y + box.height / 2) * this.scale;
      this.applyTransform();
    }
  }

  window.OpusSolutionViewer = {
    create(root) { return new SolutionViewer(root); },
    constants: { SIZE, SQRT3, COLORS, axialToPixel, hexPoints, svgEl }
  };
})();
