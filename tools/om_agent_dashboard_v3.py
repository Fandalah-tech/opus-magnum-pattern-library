from __future__ import annotations

import argparse
import re
import threading
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

import tools.om_agent_dashboard_v2 as core


def latest_elites() -> tuple[int, list[Path]]:
    elite_dir = core.WORK / "elites"
    if not elite_dir.exists():
        return 0, []
    groups: dict[int, list[tuple[int, Path]]] = {}
    rx = re.compile(r"g(\d+)-elite-(\d+)\.solution$")
    for path in elite_dir.glob("g*-elite-*.solution"):
        m = rx.match(path.name)
        if not m:
            continue
        gen, rank = map(int, m.groups())
        groups.setdefault(gen, []).append((rank, path))
    if not groups:
        return 0, []
    gen = max(groups)
    return gen, [p for _, p in sorted(groups[gen])[:3]]


def live_status() -> dict:
    s = core.status()
    gen, paths = latest_elites()
    if paths:
        top = []
        for rank, path in enumerate(paths, 1):
            top.append({
                "rank": rank,
                "cycles": s.get("bestCycles", 27),
                "cost": None,
                "area": None,
                "instructions": None,
                "mutation": f"élite #{rank}",
                "generation": gen,
                "downloadUrl": f"/download/top-{rank}.solution",
            })
        s["topSolutions"] = top
    return s


HTML = core.HTML.replace(
    "loadCfg();refresh();setInterval(refresh,1000);",
    """loadCfg();
let pollBusy=false;
async function poll(){
  if(pollBusy)return;
  pollBusy=true;
  try{await refresh()}finally{pollBusy=false;setTimeout(poll,1000)}
}
poll();""",
).replace(
    "catch(e){err('Refresh: '+e.message)}",
    "catch(e){console.warn('Refresh:',e.message)}",
).replace(
    "Disponible à la fin du run.",
    "Les 3 élites apparaissent dès la fin de chaque génération.",
)


class Handler(core.Handler):
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/":
            return self.send(HTML.encode(), "text/html; charset=utf-8")
        if p == "/api/status":
            return self.js(live_status())
        if p.startswith("/download/top-") and p.endswith(".solution"):
            m = re.match(r"/download/top-(\d+)\.solution$", p)
            if not m:
                return self.js({"message": "Solution indisponible"}, 404)
            rank = int(m.group(1))
            _, paths = latest_elites()
            if rank < 1 or rank > len(paths):
                # Fall back to final-run copies when available.
                f = core.WORK / f"top-{rank}.solution"
            else:
                f = paths[rank - 1]
            if not f.exists():
                return self.js({"message": "Solution indisponible"}, 404)
            return self.send(
                f.read_bytes(),
                "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="aqueous-live-top-{rank}.solution"'},
            )
        return super().do_GET()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    core.config()
    core.status()
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    url = f"http://{a.host}:{a.port}/"
    print(f"OM Agent dashboard v3: {url}", flush=True)
    if a.open:
        threading.Timer(.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
