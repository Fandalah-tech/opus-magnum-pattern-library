(() => {
  const NS = "http://www.w3.org/2000/svg";
  const SQRT3 = Math.sqrt(3);
  const SIZE = 34;
  const GEO = window.OpusGeometry;
  const SYMBOLS = window.OpusPieceSymbols;
  const COLORS = {
    arm: "#d4a457",
    armDark: "#3a2b1d",
    input: "#69b8a1",
    output: "#de7e63",
    track: "#8c7a61",
    trackCore: "#c6a976",
    glyph: "#9a83bb",
    selected: "#f4d58d",
    related: "#72c3b0",
    grid: "#3a342d",
    gridFill: "#161411",
    text: "#f1e8d7",
    muted: "#b8aa95"
  };
  const LAYER_ORDER = ["grid", "track", "glyph", "part", "bond", "atom", "arm", "overlay"];

  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), -SIZE * 1.5 * r];
  const hexPoints = (x, y, radius = SIZE * .9) => Array.from({ length: 6 }, (_, i) => {
    const angle = Math.PI / 180 * (60 * i - 30);
    return `${x + radius * Math.cos(angle)},${y + radius * Math.sin(angle)}`;
  }).join(" ");
  const svgEl = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };
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
      this.layers = new Map();
      this.selectedId = null;
      this.bind();
      this.buildLayers();
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

    buildLayers() {
      this.world.replaceChildren();
      this.layers.clear();
      for (const name of LAYER_ORDER) {
        const layer = svgEl("g", {
          class: `viewer-layer viewer-layer-${name}`,
          "data-viewer-layer": name
        });
        this.layers.set(name, layer);
        this.world.append(layer);
      }
    }

    layer(name) {
      if (!this.layers.has(name) || !this.layers.get(name)?.isConnected) this.buildLayers();
      return this.layers.get(name);
    }

    render(solution, graph, puzzle = null, replay = null) {
      this.parts = solution.parts || [];
      this.graph = graph || null;
      this.puzzle = puzzle || null;
      this.replay = replay || null;
      this.selectedId = null;
      this.buildLayers();
      if (!this.parts.length) {
        if (this.details) this.details.innerHTML = '<p class="hint">No parts in this solution.</p>';
        return;
      }
      this.drawGrid();
      for (const part of this.parts) this.drawPart(part);
      this.fit();
      this.selectPart(this.parts[0]?.id);
    }

    drawGrid() {
      const positions = this.parts.flatMap((part) => GEO.occupiedCells(part));
      const qs = positions.map(([q]) => q);
      const rs = positions.map(([, r]) => r);
      const minQ = Math.min(...qs) - 5;
      const maxQ = Math.max(...qs) + 5;
      const minR = Math.min(...rs) - 5;
      const maxR = Math.max(...rs) + 5;
      const grid = this.layer("grid");
      for (let q = minQ; q <= maxQ; q += 1) {
        for (let r = minR; r <= maxR; r += 1) {
          const [x, y] = axialToPixel([q, r]);
          const active = positions.some(([pq, pr]) => pq === q && pr === r);
          grid.append(svgEl("polygon", {
            points: hexPoints(x, y, SIZE * .92),
            fill: active ? COLORS.gridFill : "transparent",
            "fill-opacity": active ? .72 : 0,
            stroke: COLORS.grid,
            "stroke-width": active ? 1.35 : .9,
            "stroke-opacity": active ? .9 : .58,
            class: active ? "viewer-grid-cell active" : "viewer-grid-cell"
          }));
        }
      }
    }

    drawPart(part) {
      const kind = this.kind(part.type);
      const targetLayer = kind === "track" ? "track" : kind === "arm" ? "arm" : kind === "glyph" ? "glyph" : "part";
      const group = svgEl("g", {
        "data-part-id": part.id,
        "data-part-kind": kind,
        class: `viewer-part viewer-${kind}`,
        tabindex: 0,
        role: "button",
        "aria-label": `${part.type} ${part.id}`
      });
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        this.selectPart(part.id);
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.selectPart(part.id);
        }
      });
      group.addEventListener("pointerenter", () => group.classList.add("hovered"));
      group.addEventListener("pointerleave", () => group.classList.remove("hovered"));

      if (kind === "track") this.drawTrack(group, part);
      else if (kind === "arm") this.drawArm(group, part);
      else this.drawStation(group, part, kind);

      const title = svgEl("title");
      title.textContent = `${part.type} · ${part.id}`;
      group.append(title);
      this.layer(targetLayer).append(group);
    }

    drawTrack(group, part) {
      const cells = GEO.occupiedCells(part);
      const points = cells.map(axialToPixel).map(([x, y]) => `${x},${y}`).join(" ");
      group.append(svgEl("polyline", {
        points,
        fill: "none",
        stroke: "#211d18",
        "stroke-width": 17,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        class: "viewer-track-shadow"
      }));
      group.append(svgEl("polyline", {
        points,
        fill: "none",
        stroke: COLORS.track,
        "stroke-width": 10,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        class: "viewer-track-rail"
      }));
      group.append(svgEl("polyline", {
        points,
        fill: "none",
        stroke: COLORS.trackCore,
        "stroke-width": 2.4,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "stroke-dasharray": "3 8",
        class: "viewer-track-core"
      }));
      for (const cell of cells) {
        const [x, y] = axialToPixel(cell);
        group.append(svgEl("circle", { cx: x, cy: y, r: 5.5, fill: "#241f19", stroke: COLORS.trackCore, "stroke-width": 2 }));
      }
    }

    drawArm(group, part) {
      const origin = part.position || [0, 0];
      const [x, y] = axialToPixel(origin);
      const branchOffsets = part.type === "arm6" ? [0, 1, 2, 3, 4, 5] : [0];
      const length = Math.max(1, Number(part.length || 1));
      group.dataset.branchCount = String(branchOffsets.length);

      for (let branchIndex = 0; branchIndex < branchOffsets.length; branchIndex += 1) {
        const rotation = Number(part.rotation || 0) + branchOffsets[branchIndex];
        const [dq, dr] = GEO.direction(rotation);
        const [ex, ey] = axialToPixel([origin[0] + dq * length, origin[1] + dr * length]);
        group.append(svgEl("line", {
          x1: x, y1: y, x2: ex, y2: ey,
          stroke: "#1f1a14", "stroke-width": 13, "stroke-linecap": "round",
          "data-arm-shadow": branchIndex
        }));
        group.append(svgEl("line", {
          x1: x, y1: y, x2: ex, y2: ey,
          stroke: COLORS.arm, "stroke-width": 7, "stroke-linecap": "round",
          "data-arm-shaft": branchIndex
        }));
        group.append(svgEl("circle", {
          cx: ex, cy: ey, r: 11.5, fill: COLORS.armDark, stroke: COLORS.arm, "stroke-width": 4,
          "data-arm-tip": branchIndex
        }));
        group.append(svgEl("circle", {
          cx: ex, cy: ey, r: 4.2, fill: COLORS.arm,
          "data-arm-grip": branchIndex
        }));
      }
      group.append(svgEl("circle", {
        cx: x, cy: y, r: 17, fill: "#1b1814", stroke: "#5a452d", "stroke-width": 6,
        class: "viewer-arm-base-shadow"
      }));
      group.append(svgEl("circle", {
        cx: x, cy: y, r: 14, fill: COLORS.armDark, stroke: COLORS.arm, "stroke-width": 3.5,
        "data-arm-base": "true"
      }));
      group.append(svgEl("circle", { cx: x, cy: y, r: 4.5, fill: COLORS.arm }));
    }

    drawStation(group, part, kind) {
      const cells = GEO.occupiedCells(part);
      const color = COLORS[kind] || COLORS.glyph;
      const centers = cells.map(axialToPixel);
      const footprint = svgEl("g", { class: "viewer-piece-footprint" });
      for (const [x, y] of centers) {
        footprint.append(svgEl("polygon", {
          points: hexPoints(x, y, SIZE * .72),
          fill: color,
          "fill-opacity": .09,
          stroke: color,
          "stroke-opacity": .78,
          "stroke-width": 2.2
        }));
        footprint.append(svgEl("polygon", {
          points: hexPoints(x, y, SIZE * .58),
          fill: "#12100e",
          "fill-opacity": .74,
          stroke: "#251f19",
          "stroke-width": 1
        }));
      }
      group.append(footprint);
      if (SYMBOLS?.draw) {
        SYMBOLS.draw(group, part, centers, color, GEO.label(part.type));
      } else {
        const [cx, cy] = axialToPixel(part.position || [0, 0]);
        const label = svgEl("text", { x: cx, y: cy + 5, "text-anchor": "middle", fill: COLORS.text, "font-size": 12, "font-weight": 700 });
        label.textContent = GEO.label(part.type);
        group.append(label);
      }
    }

    relationSet(id) {
      const related = new Set();
      for (const edge of this.graph?.edges || []) {
        if (edge.source === id) related.add(edge.target);
        if (edge.target === id) related.add(edge.source);
      }
      return related;
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
      for (const cell of GEO.occupiedCells(part)) {
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
      const footprint = GEO.occupiedCells(part);
      const rows = this.commonRows(part);
      if (kind === "arm") {
        rows.push(
          ["Length", part.length ?? 1],
          ["Arm number", part.armNumber ?? "—"],
          ["Branches", part.type === "arm6" ? 6 : 1],
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
      const kind = this.kind(part.type);
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
        ["Held by", Array.isArray(molecule.heldBy) && molecule.heldBy.length ? molecule.heldBy.join(", ") : "None"]
      ];
      const atoms = (molecule.atoms || []).map((atom) => `<li><b>${escapeHtml(atom.element)}</b><span>${escapeHtml(formatPosition(atom.position))}</span></li>`).join("");
      this.details.innerHTML = `<header class="viewer-inspector-head"><span class="viewer-kind-badge molecule">molecule</span><div><h4>Molecule</h4><p>${escapeHtml(molecule.id)}</p></div></header><section class="viewer-inspector-section"><h5>Properties</h5><dl>${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></section>${atoms ? `<section class="viewer-inspector-section"><h5>Atoms</h5><ul class="viewer-related-list">${atoms}</ul></section>` : ""}`;
    }

    kind(type = "") {
      if (/^(arm|piston|baron)/.test(type)) return "arm";
      if (type === "input") return "input";
      if (type.startsWith("out-")) return "output";
      if (type === "track") return "track";
      if (type === "conduit") return "conduit";
      if (type.startsWith("glyph-") || type === "bonder" || type === "unbonder") return "glyph";
      return "part";
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