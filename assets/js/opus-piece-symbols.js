(() => {
  const NS = "http://www.w3.org/2000/svg";
  const el = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };
  const line = (x1, y1, x2, y2, stroke, width = 3) => el("line", { x1, y1, x2, y2, stroke, "stroke-width": width, "stroke-linecap": "round" });
  const circle = (cx, cy, r, stroke, fill = "none", width = 3) => el("circle", { cx, cy, r, stroke, fill, "stroke-width": width });

  function drawBond(group, centers, color, broken = false) {
    if (centers.length < 2) return;
    const [a, b] = centers;
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    group.append(line(a[0], a[1], b[0], b[1], color, 5));
    group.append(circle(a[0], a[1], 8, color, "#171512", 3));
    group.append(circle(b[0], b[1], 8, color, "#171512", 3));
    if (broken) {
      group.append(line(mx - 7, my - 7, mx + 7, my + 7, "#efe7d7", 3));
      group.append(line(mx - 7, my + 7, mx + 7, my - 7, "#efe7d7", 3));
    }
  }

  function drawCalcification(group, [x, y], color) {
    group.append(circle(x, y, 15, color, "none", 3));
    group.append(line(x - 10, y, x + 10, y, color, 3));
    group.append(line(x, y - 10, x, y + 10, color, 3));
    group.append(line(x - 7, y - 7, x + 7, y + 7, color, 2));
    group.append(line(x - 7, y + 7, x + 7, y - 7, color, 2));
  }

  function drawInputOutput(group, [x, y], color, output) {
    group.append(circle(x, y, 15, color, "#171512", 3));
    const path = output
      ? `M ${x - 7} ${y - 9} L ${x + 9} ${y} L ${x - 7} ${y + 9} Z`
      : `M ${x + 7} ${y - 9} L ${x - 9} ${y} L ${x + 7} ${y + 9} Z`;
    group.append(el("path", { d: path, fill: color }));
  }

  function drawGeneric(group, centers, color, label) {
    for (const [x, y] of centers) group.append(circle(x, y, 10, color, "#171512", 2));
    if (centers.length > 1) {
      for (let i = 1; i < centers.length; i += 1) group.append(line(centers[0][0], centers[0][1], centers[i][0], centers[i][1], color, 3));
    }
    const [x, y] = centers[0];
    const text = el("text", { x, y: y + 4, "text-anchor": "middle", fill: "#efe7d7", "font-size": 10, "font-weight": 700 });
    text.textContent = label;
    group.append(text);
  }

  function draw(group, part, centers, color, label) {
    if (!centers.length) return;
    switch (part.type) {
      case "bonder": drawBond(group, centers, color, false); break;
      case "unbonder": drawBond(group, centers, color, true); break;
      case "glyph-calcification": drawCalcification(group, centers[0], color); break;
      case "input": drawInputOutput(group, centers[0], color, false); break;
      case "out-std":
      case "out-rep": drawInputOutput(group, centers[0], color, true); break;
      default: drawGeneric(group, centers, color, label); break;
    }
  }

  window.OpusPieceSymbols = { draw };
})();