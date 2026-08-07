(() => {
  const NS = "http://www.w3.org/2000/svg";
  const el = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };
  const line = (x1, y1, x2, y2, stroke, width = 3, extra = {}) => el("line", { x1, y1, x2, y2, stroke, "stroke-width": width, "stroke-linecap": "round", ...extra });
  const circle = (cx, cy, r, stroke, fill = "none", width = 3, extra = {}) => el("circle", { cx, cy, r, stroke, fill, "stroke-width": width, ...extra });
  const path = (d, stroke, width = 3, fill = "none", extra = {}) => el("path", { d, stroke, "stroke-width": width, fill, "stroke-linecap": "round", "stroke-linejoin": "round", ...extra });

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

  function drawMultiBond(group, centers, color) {
    if (!centers.length) return;
    const [hub, ...outer] = centers;
    for (const point of outer) group.append(line(hub[0], hub[1], point[0], point[1], color, 4));
    group.append(circle(hub[0], hub[1], 9, color, "#171512", 3));
    for (const [x, y] of outer) group.append(circle(x, y, 7, color, "#171512", 2.5));
    group.append(circle(hub[0], hub[1], 3, "#efe7d7", color, 1));
  }

  function drawCalcification(group, [x, y], color) {
    group.append(circle(x, y, 15, color, "none", 3));
    group.append(line(x - 10, y, x + 10, y, color, 3));
    group.append(line(x, y - 10, x, y + 10, color, 3));
    group.append(line(x - 7, y - 7, x + 7, y + 7, color, 2));
    group.append(line(x - 7, y + 7, x + 7, y - 7, color, 2));
  }

  function drawEquilibrium(group, [x, y], color) {
    group.append(circle(x, y, 15, color, "#171512", 2.5));
    group.append(line(x - 10, y - 5, x + 10, y - 5, color, 2.5));
    group.append(line(x, y - 10, x, y + 9, color, 2.5));
    group.append(path(`M ${x-10} ${y-5} Q ${x-7} ${y+5} ${x-3} ${y-5} M ${x+3} ${y-5} Q ${x+7} ${y+5} ${x+10} ${y-5}`, color, 2));
  }

  function drawDisposal(group, centers, color) {
    if (!centers.length) return;
    const [hub, ...outer] = centers;
    for (const point of outer) {
      const dx = hub[0] - point[0], dy = hub[1] - point[1];
      const mag = Math.hypot(dx, dy) || 1;
      const ex = hub[0] - dx / mag * 10, ey = hub[1] - dy / mag * 10;
      group.append(line(point[0], point[1], ex, ey, color, 2.5));
    }
    group.append(circle(hub[0], hub[1], 12, color, "#171512", 3));
    group.append(path(`M ${hub[0]-6} ${hub[1]-6} L ${hub[0]+6} ${hub[1]+6} M ${hub[0]-6} ${hub[1]+6} L ${hub[0]+6} ${hub[1]-6}`, "#efe7d7", 2.5));
  }

  function drawProjection(group, centers, color) {
    if (centers.length < 2) return;
    const [a, b] = centers;
    const mx = (a[0]+b[0])/2, my=(a[1]+b[1])/2;
    group.append(circle(a[0], a[1], 8, color, "#171512", 2.5));
    group.append(circle(b[0], b[1], 8, color, "#171512", 2.5));
    group.append(line(a[0]+8, a[1], b[0]-8, b[1], color, 3));
    group.append(path(`M ${mx-3} ${my-6} L ${mx+5} ${my} L ${mx-3} ${my+6}`, "#efe7d7", 2));
  }

  function drawPurification(group, centers, color) {
    if (centers.length < 3) return;
    const [a,b,c] = centers;
    group.append(line(a[0],a[1],b[0],b[1],color,3));
    group.append(line(b[0],b[1],c[0],c[1],color,3));
    group.append(circle(a[0],a[1],7,color,"#171512",2));
    group.append(circle(c[0],c[1],7,color,"#171512",2));
    group.append(circle(b[0],b[1],11,color,"#171512",3));
    group.append(path(`M ${b[0]} ${b[1]-7} L ${b[0]+6} ${b[1]+5} L ${b[0]-6} ${b[1]+5} Z`, "#efe7d7", 1.8, "none"));
  }

  function drawDuplication(group, centers, color) {
    if (centers.length < 2) return;
    const [a,b]=centers;
    const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2;
    group.append(line(a[0],a[1],b[0],b[1],color,3));
    group.append(circle(a[0],a[1],9,color,"#171512",2.5));
    group.append(circle(b[0],b[1],9,color,"#171512",2.5));
    group.append(path(`M ${mx-5} ${my-6} L ${mx+2} ${my} L ${mx-5} ${my+6} M ${mx+1} ${my-6} L ${mx+8} ${my} L ${mx+1} ${my+6}`, "#efe7d7", 1.8));
  }

  function drawLifeDeath(group, centers, color) {
    if (centers.length < 2) return;
    const [a,b]=centers;
    group.append(line(a[0],a[1],b[0],b[1],color,3));
    group.append(circle(a[0],a[1],10,color,"#171512",2.5));
    group.append(circle(a[0],a[1],4,"#efe7d7",color,1));
    group.append(circle(b[0],b[1],10,color,"#171512",2.5));
    group.append(line(b[0]-5,b[1]-5,b[0]+5,b[1]+5,"#efe7d7",2));
    group.append(line(b[0]-5,b[1]+5,b[0]+5,b[1]-5,"#efe7d7",2));
  }

  function drawPrisma(group, centers, color, broken = false) {
    if (centers.length < 3) return;
    const [a,b,c]=centers;
    group.append(line(a[0],a[1],b[0],b[1],color,3));
    group.append(line(b[0],b[1],c[0],c[1],color,3));
    group.append(line(c[0],c[1],a[0],a[1],color,3));
    for (const [x,y] of centers) group.append(circle(x,y,7,color,"#171512",2));
    if (broken) {
      const x=(a[0]+b[0]+c[0])/3,y=(a[1]+b[1]+c[1])/3;
      group.append(line(x-5,y-5,x+5,y+5,"#efe7d7",2));
      group.append(line(x-5,y+5,x+5,y-5,"#efe7d7",2));
    }
  }

  function drawInputOutput(group, [x, y], color, output) {
    group.append(circle(x, y, 15, color, "#171512", 3));
    const d = output
      ? `M ${x - 7} ${y - 9} L ${x + 9} ${y} L ${x - 7} ${y + 9} Z`
      : `M ${x + 7} ${y - 9} L ${x - 9} ${y} L ${x + 7} ${y + 9} Z`;
    group.append(el("path", { d, fill: color }));
  }

  function drawGeneric(group, centers, color, label) {
    for (const [x, y] of centers) group.append(circle(x, y, 10, color, "#171512", 2));
    if (centers.length > 1) for (let i = 1; i < centers.length; i += 1) group.append(line(centers[0][0], centers[0][1], centers[i][0], centers[i][1], color, 3));
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
      case "bonder-speed": drawMultiBond(group, centers, color); break;
      case "glyph-calcification": drawCalcification(group, centers[0], color); break;
      case "glyph-equilibrium": drawEquilibrium(group, centers[0], color); break;
      case "glyph-disposal": drawDisposal(group, centers, color); break;
      case "glyph-projection": drawProjection(group, centers, color); break;
      case "glyph-purification": drawPurification(group, centers, color); break;
      case "glyph-duplication": drawDuplication(group, centers, color); break;
      case "glyph-life-and-death": drawLifeDeath(group, centers, color); break;
      case "glyph-bonder-prisma": drawPrisma(group, centers, color, false); break;
      case "glyph-unbonder-prisma": drawPrisma(group, centers, color, true); break;
      case "input": drawInputOutput(group, centers[0], color, false); break;
      case "out-std":
      case "out-rep": drawInputOutput(group, centers[0], color, true); break;
      default: drawGeneric(group, centers, color, label); break;
    }
  }

  window.OpusPieceSymbols = { draw };
})();
