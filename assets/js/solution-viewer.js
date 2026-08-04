(() => {
  const NS = "http://www.w3.org/2000/svg";
  const SQRT3 = Math.sqrt(3);
  const SIZE = 34;
  const GEO = window.OpusGeometry;
  const COLORS = {
    arm: "#d8a653", input: "#74b9a5", output: "#d97b68", track: "#8f8577",
    glyph: "#b397cc", selected: "#f5d58f", grid: "#302c27", text: "#efe7d7"
  };

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

  class SolutionViewer {
    constructor(root) {
      this.root = root;
      this.svg = root.querySelector("svg");
      this.world = root.querySelector("[data-viewer-world]");
      this.details = root.querySelector("[data-viewer-details]");
      this.zoomLabel = root.querySelector("[data-viewer-zoom]");
      this.scale = 1; this.tx = 0; this.ty = 0; this.drag = null;
      this.parts = []; this.graph = null;
      this.bind();
    }

    bind() {
      this.root.querySelector("[data-viewer-fit]")?.addEventListener("click", () => this.fit());
      this.root.querySelector("[data-viewer-reset]")?.addEventListener("click", () => {
        this.scale = 1; this.tx = 0; this.ty = 0; this.applyTransform();
      });
      this.svg.addEventListener("wheel", (event) => {
        event.preventDefault();
        this.scale = Math.max(.25, Math.min(4, this.scale * (event.deltaY < 0 ? 1.12 : .89)));
        this.applyTransform();
      }, { passive: false });
      this.svg.addEventListener("pointerdown", (event) => {
        if (event.target.closest("[data-part-id]")) return;
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
    }

    render(solution, graph) {
      this.parts = solution.parts || [];
      this.graph = graph || null;
      this.world.replaceChildren();
      if (!this.parts.length) return;
      this.drawGrid();
      for (const part of this.parts) this.drawPart(part);
      this.fit();
      this.selectPart(this.parts[0]?.id);
    }

    drawGrid() {
      const positions = this.parts.flatMap((part) => GEO.occupiedCells(part));
      const qs = positions.map(([q]) => q), rs = positions.map(([, r]) => r);
      const minQ = Math.min(...qs) - 4, maxQ = Math.max(...qs) + 4;
      const minR = Math.min(...rs) - 4, maxR = Math.max(...rs) + 4;
      const grid = svgEl("g", { class: "viewer-grid" });
      for (let q = minQ; q <= maxQ; q += 1) for (let r = minR; r <= maxR; r += 1) {
        const [x, y] = axialToPixel([q, r]);
        grid.append(svgEl("polygon", { points: hexPoints(x, y), fill: "none", stroke: COLORS.grid, "stroke-width": 1 }));
      }
      this.world.append(grid);
    }

    drawPart(part) {
      const kind = this.kind(part.type);
      const group = svgEl("g", { "data-part-id": part.id, class: `viewer-part viewer-${kind}`, tabindex: 0, role: "button" });
      group.addEventListener("click", () => this.selectPart(part.id));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") this.selectPart(part.id);
      });

      if (kind === "track") this.drawTrack(group, part);
      else if (kind === "arm") this.drawArm(group, part);
      else this.drawStation(group, part, kind);

      const title = svgEl("title");
      title.textContent = `${part.type} · ${part.id}`;
      group.append(title);
      this.world.append(group);
    }

    drawTrack(group, part) {
      const cells = GEO.occupiedCells(part);
      const points = cells.map(axialToPixel).map(([x, y]) => `${x},${y}`).join(" ");
      group.append(svgEl("polyline", { points, fill: "none", stroke: COLORS.track, "stroke-width": 11, "stroke-linecap": "round", "stroke-linejoin": "round" }));
      for (const cell of cells) {
        const [x, y] = axialToPixel(cell);
        group.append(svgEl("circle", { cx: x, cy: y, r: 7, fill: COLORS.track }));
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
          stroke: COLORS.arm, "stroke-width": 8, "stroke-linecap": "round",
          "data-arm-shaft": branchIndex
        }));
        group.append(svgEl("circle", {
          cx: ex, cy: ey, r: 10, fill: COLORS.arm,
          "data-arm-tip": branchIndex
        }));
      }
      group.append(svgEl("circle", {
        cx: x, cy: y, r: 15, fill: "#2b2722", stroke: COLORS.arm, "stroke-width": 4,
        "data-arm-base": "true"
      }));
    }

    drawStation(group, part, kind) {
      const cells = GEO.occupiedCells(part);
      const color = COLORS[kind] || COLORS.glyph;
      for (const cell of cells) {
        const [x, y] = axialToPixel(cell);
        group.append(svgEl("polygon", { points: hexPoints(x, y, SIZE * .72), fill: color, "fill-opacity": .20, stroke: color, "stroke-width": 3 }));
      }
      const [cx, cy] = axialToPixel(part.position || [0, 0]);
      const label = svgEl("text", { x: cx, y: cy + 5, "text-anchor": "middle", fill: COLORS.text, "font-size": 12, "font-weight": 700 });
      label.textContent = GEO.label(part.type);
      group.append(label);
    }

    selectPart(id) {
      this.world.querySelectorAll("[data-part-id]").forEach((node) => node.classList.toggle("selected", node.dataset.partId === id));
      const part = this.parts.find((item) => item.id === id);
      if (!part || !this.details) return;
      const relations = (this.graph?.edges || []).filter((edge) => edge.source === id || edge.target === id);
      const program = part.program || [];
      const footprint = GEO.occupiedCells(part);
      const rows = [
        ["Type", part.type], ["ID", part.id], ["Position", `(${part.position?.join(", ") || "—"})`],
        ["Rotation", part.rotation ?? 0], ["Length", part.length ?? 1], ["Arm number", part.armNumber ?? "—"],
        ["Branches", part.type === "arm6" ? 6 : 1],
        ["Footprint", footprint.map(([q, r]) => `(${q}, ${r})`).join(" ")], ["Instructions", program.length], ["Relations", relations.length]
      ];
      this.details.innerHTML = `<h4>${part.type}</h4><dl>${rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("")}</dl>${program.length ? `<h5>Program</h5><ol>${program.slice(0, 80).map((item) => `<li><b>${item.cycle}</b> ${item.instruction}</li>`).join("")}</ol>` : ""}`;
    }

    kind(type = "") {
      if (/^(arm|piston|baron)/.test(type)) return "arm";
      if (type === "input") return "input";
      if (type.startsWith("out-")) return "output";
      if (type === "track") return "track";
      return "glyph";
    }

    applyTransform() {
      this.world.setAttribute("transform", `translate(${this.tx} ${this.ty}) scale(${this.scale})`);
      if (this.zoomLabel) this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    }

    fit() {
      const box = this.world.getBBox();
      const width = this.svg.clientWidth || 900, height = this.svg.clientHeight || 560;
      if (!box.width || !box.height) return;
      this.scale = Math.max(.25, Math.min(2.4, Math.min((width - 80) / box.width, (height - 80) / box.height)));
      this.tx = width / 2 - (box.x + box.width / 2) * this.scale;
      this.ty = height / 2 - (box.y + box.height / 2) * this.scale;
      this.applyTransform();
    }
  }

  window.OpusSolutionViewer = { create(root) { return new SolutionViewer(root); } };
})();