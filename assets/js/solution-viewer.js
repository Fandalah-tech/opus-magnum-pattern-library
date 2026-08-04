(() => {
  const NS = "http://www.w3.org/2000/svg";
  const SQRT3 = Math.sqrt(3);
  const SIZE = 34;
  const COLORS = {
    arm: "#d8a653", input: "#74b9a5", output: "#d97b68", track: "#8f8577",
    glyph: "#b397cc", selected: "#f5d58f", grid: "#302c27", text: "#efe7d7"
  };

  const axialToPixel = ([q, r]) => [SIZE * SQRT3 * (q + r / 2), SIZE * 1.5 * r];
  const hexPoints = (x, y, radius = SIZE * .9) => Array.from({ length: 6 }, (_, i) => {
    const a = Math.PI / 180 * (60 * i - 30);
    return `${x + radius * Math.cos(a)},${y + radius * Math.sin(a)}`;
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
      this.scale = 1;
      this.tx = 0;
      this.ty = 0;
      this.drag = null;
      this.parts = [];
      this.bind();
    }

    bind() {
      this.root.querySelector("[data-viewer-fit]")?.addEventListener("click", () => this.fit());
      this.root.querySelector("[data-viewer-reset]")?.addEventListener("click", () => { this.scale = 1; this.tx = 0; this.ty = 0; this.applyTransform(); });
      this.svg.addEventListener("wheel", (event) => {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.12 : .89;
        this.scale = Math.max(.25, Math.min(4, this.scale * factor));
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
      this.world.replaceChildren();
      if (!this.parts.length) return;
      this.drawGrid();
      for (const part of this.parts) this.drawPart(part);
      this.fit();
      this.selectPart(this.parts[0]?.id, graph);
    }

    drawGrid() {
      const positions = this.parts.flatMap((part) => [part.position || [0, 0], ...(part.trackHexes || []).map(([q, r]) => [(part.position?.[0] || 0) + q, (part.position?.[1] || 0) + r])]);
      const qs = positions.map((p) => p[0]), rs = positions.map((p) => p[1]);
      const minQ = Math.min(...qs) - 4, maxQ = Math.max(...qs) + 4;
      const minR = Math.min(...rs) - 4, maxR = Math.max(...rs) + 4;
      const grid = svgEl("g", { class: "viewer-grid" });
      for (let q = minQ; q <= maxQ; q++) for (let r = minR; r <= maxR; r++) {
        const [x, y] = axialToPixel([q, r]);
        grid.append(svgEl("polygon", { points: hexPoints(x, y), fill: "none", stroke: COLORS.grid, "stroke-width": 1 }));
      }
      this.world.append(grid);
    }

    drawPart(part) {
      const [x, y] = axialToPixel(part.position || [0, 0]);
      const kind = this.kind(part.type);
      const group = svgEl("g", { "data-part-id": part.id, class: `viewer-part viewer-${kind}`, tabindex: 0, role: "button" });
      group.addEventListener("click", () => this.selectPart(part.id));
      group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") this.selectPart(part.id); });

      if (kind === "track") {
        const cells = [[0, 0], ...(part.trackHexes || [])];
        const points = cells.map(([dq, dr]) => axialToPixel([(part.position?.[0] || 0) + dq, (part.position?.[1] || 0) + dr])).map(([px, py]) => `${px},${py}`).join(" ");
        group.append(svgEl("polyline", { points, fill: "none", stroke: COLORS.track, "stroke-width": 11, "stroke-linecap": "round", "stroke-linejoin": "round" }));
        for (const [dq, dr] of cells) {
          const [px, py] = axialToPixel([(part.position?.[0] || 0) + dq, (part.position?.[1] || 0) + dr]);
          group.append(svgEl("circle", { cx: px, cy: py, r: 7, fill: COLORS.track }));
        }
      } else if (kind === "arm") {
        const rotation = Number(part.rotation || 0);
        const angle = Math.PI / 3 * rotation - Math.PI / 6;
        const reach = SIZE * Math.max(1, Number(part.length || 1));
        const ex = x + Math.cos(angle) * reach;
        const ey = y + Math.sin(angle) * reach;
        group.append(svgEl("circle", { cx: x, cy: y, r: 15, fill: "#2b2722", stroke: COLORS.arm, "stroke-width": 4 }));
        group.append(svgEl("line", { x1: x, y1: y, x2: ex, y2: ey, stroke: COLORS.arm, "stroke-width": 8, "stroke-linecap": "round" }));
        group.append(svgEl("circle", { cx: ex, cy: ey, r: 10, fill: COLORS.arm }));
      } else {
        group.append(svgEl("polygon", { points: hexPoints(x, y, SIZE * .72), fill: COLORS[kind] || COLORS.glyph, "fill-opacity": .24, stroke: COLORS[kind] || COLORS.glyph, "stroke-width": 3 }));
        const label = svgEl("text", { x, y: y + 5, "text-anchor": "middle", fill: COLORS.text, "font-size": 12, "font-weight": 700 });
        label.textContent = this.shortLabel(part.type);
        group.append(label);
      }
      const title = svgEl("title"); title.textContent = `${part.type} · ${part.id}`; group.append(title);
      this.world.append(group);
    }

    selectPart(id, graph = null) {
      this.world.querySelectorAll("[data-part-id]").forEach((node) => node.classList.toggle("selected", node.dataset.partId === id));
      const part = this.parts.find((item) => item.id === id);
      if (!part || !this.details) return;
      const node = graph?.nodes?.find((item) => item.id === id);
      const program = part.program || [];
      const rows = [
        ["Type", part.type], ["ID", part.id], ["Position", `(${part.position?.join(", ") || "—"})`],
        ["Rotation", part.rotation ?? 0], ["Length", part.length ?? 1], ["Arm number", part.armNumber ?? "—"],
        ["Instructions", program.length], ["Relations", node ? "available in graph" : "—"]
      ];
      this.details.innerHTML = `<h4>${part.type}</h4><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>${program.length ? `<h5>Program</h5><ol>${program.slice(0, 80).map((item) => `<li><b>${item.cycle}</b> ${item.instruction}</li>`).join("")}</ol>` : ""}`;
    }

    kind(type = "") {
      if (/^(arm|piston|baron)/.test(type)) return "arm";
      if (type === "input") return "input";
      if (type.startsWith("out-")) return "output";
      if (type === "track") return "track";
      return "glyph";
    }
    shortLabel(type = "") {
      if (type === "input") return "IN";
      if (type.startsWith("out-")) return "OUT";
      return type.replace("glyph-", "").replace(/[^a-z0-9]/gi, " ").split(" ").map((s) => s[0]).join("").slice(0, 3).toUpperCase();
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