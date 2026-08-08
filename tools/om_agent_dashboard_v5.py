from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

import tools.om_agent_dashboard_v2 as core


# Fresh runtime: never mix Top files/status from v2-v4 runs.
RUNTIME = Path(os.environ.get("LOCALAPPDATA", core.ROOT / ".runtime")) / "OpusMagnumAgent" / "dashboard-v5"
RUNTIME.mkdir(parents=True, exist_ok=True)
core.RUNTIME = RUNTIME
core.STATUS = RUNTIME / "status.json"
core.CONFIG = RUNTIME / "config.json"
core.LOG = RUNTIME / "solver.log"
core.WORK = RUNTIME / "aqueous-v5"
core.PUZZLE = RUNTIME / "aqueous-dagger.puzzle"
core.SEED = RUNTIME / "single27.solution"
core.DEFAULT_CONFIG["workers"] = 8
core.DEFAULT_CONFIG["generations"] = 200
core.DEFAULT_CONFIG["stagnation"] = 0


def safe_config() -> dict:
    c = {**core.DEFAULT_CONFIG, **core.read_json(core.CONFIG, core.DEFAULT_CONFIG)}
    c["workers"] = max(1, min(8, int(c.get("workers", 8))))
    c["generations"] = max(1, int(c.get("generations", 200)))
    core.write_json(core.CONFIG, c)
    return c


core.config = safe_config


def checkpoint() -> dict:
    p = core.WORK / "checkpoint.json"
    return core.read_json(p, {}) if p.exists() else {}


def load_top_v5() -> list[dict]:
    cp = checkpoint()
    top = cp.get("top") or []
    out = []
    for rank, item in enumerate(top[:3], 1):
        f = core.WORK / f"top-{rank}.solution"
        if not f.exists():
            continue
        m = item.get("metrics") or {}
        out.append({
            "rank": rank,
            "cycles": m.get("cycles"),
            "cost": m.get("cost"),
            "area": m.get("area"),
            "instructions": m.get("instructions"),
            "mutation": item.get("kind") or "candidate",
            "generation": item.get("generation", 0),
            "downloadUrl": f"/download/top-{rank}.solution",
        })
    return out


def status_v5() -> dict:
    s = core.status()
    cp = checkpoint()
    if cp:
        s["bestCycles"] = cp.get("bestCycles", s.get("bestCycles", 27))
        s["tested"] = cp.get("tested", s.get("tested", 0))
        s["valid"] = cp.get("valid", s.get("valid", 0))
        s["topSolutions"] = load_top_v5()
        s["attemptedMechanisms"] = cp.get("attemptedMechanisms", 0)
        s["validMechanisms"] = cp.get("validMechanisms", 0)
        s["expandedParents"] = cp.get("expandedParents", 0)
        s["frontier"] = cp.get("frontier", 0)
        s["timeouts"] = cp.get("timeouts", 0)
    return s


_original_parse = core.parse_line


def parse_line_v5(line: str) -> None:
    m = re.search(
        r"DIVERSITY generation=(\d+)/(\d+) parents=(\d+) generated=(\d+) new=(\d+) repeatPrior=(\d+) duplicateWithin=(\d+) translationClasses=(\d+) attemptedBefore=(\d+) validArchive=(\d+)",
        line,
    )
    if m:
        g, mg, parents, generated, new, repeat, dup, tc, attempted, archive = map(int, m.groups())
        core.patch_status(
            generation=g, maxGenerations=mg, generationTested=0, generationTotal=new,
            generatedRaw=generated, newMechanisms=new, repeatPrior=repeat,
            duplicateWithin=dup, translationClasses=tc, attemptedMechanisms=attempted,
            validMechanisms=archive,
            message=f"G{g} · {new} nouveaux / {generated} générés · {repeat} déjà testés",
        )
        return
    m = re.search(
        r"PROGRESS generation=(\d+)/(\d+) tested=(\d+)/(\d+) cumulative=(\d+) valid=(\d+) best=(\d+) attempted=(\d+) archive=(\d+)",
        line,
    )
    if m:
        g, mg, tested, total, cumulative, valid, best, attempted, archive = map(int, m.groups())
        core.patch_status(
            generation=g, maxGenerations=mg, generationTested=tested, generationTotal=total,
            tested=cumulative, generationValid=valid, bestCycles=best,
            attemptedMechanisms=attempted, validMechanisms=archive,
            message=f"Recherche G{g}/{mg} · {tested}/{total}",
        )
        return
    m = re.search(
        r"HEARTBEAT generation=(\d+)/(\d+) tested=(\d+)/(\d+) active=(\d+) notStarted=(\d+) idle=([0-9.]+)s elapsed=([0-9.]+)s timeouts=(\d+)",
        line,
    )
    if m:
        g, mg, tested, total, active, not_started, idle, elapsed, timeouts = m.groups()
        core.patch_status(
            generation=int(g), maxGenerations=int(mg), generationTested=int(tested), generationTotal=int(total),
            activeValidations=int(active), notStarted=int(not_started), idleSeconds=float(idle),
            generationElapsed=float(elapsed), generationTimeouts=int(timeouts),
            message=f"Actif · {active} validations · idle {idle}s · {not_started} non démarrés",
        )
        return
    if line.startswith("WATCHDOG "):
        core.patch_status(message=line)
        return
    m = re.search(
        r"CHECKPOINT generation=(\d+) best=(\d+) distinctTop=(\d+) attempted=(\d+) validArchive=(\d+) expanded=(\d+) frontier=(\d+) aborted=(\d+)",
        line,
    )
    if m:
        g, best, top, attempted, archive, expanded, frontier, aborted = map(int, m.groups())
        core.patch_status(
            generation=g, bestCycles=best, distinctTop=top, attemptedMechanisms=attempted,
            validMechanisms=archive, expandedParents=expanded, frontier=frontier,
            topSolutions=load_top_v5(),
            message=f"Checkpoint G{g} · {attempted} mécanismes tentés · frontier {frontier}",
        )
        return
    _original_parse(line)


core.parse_line = parse_line_v5


def start_solver_v5() -> tuple[bool, str]:
    with core._lock:
        if core._proc is not None and core._proc.poll() is None:
            return False, "Le solveur est déjà actif."
        c = safe_config()
        core.materialize()
        if core.WORK.exists():
            shutil.rmtree(core.WORK)
        core.LOG.write_text("", encoding="utf-8")
        cmd = [
            sys.executable, "tools/run_aqueous_evolution_v5.py",
            "--validator-url", str(c["validatorUrl"]),
            "--puzzle", str(core.PUZZLE), "--seed", str(core.SEED), "--work", str(core.WORK),
            "--generations", str(c["generations"]), "--elites", str(max(1, int(c["elites"]))),
            "--target-cycles", str(int(c["targetCycles"])), "--workers", str(c["workers"]),
            "--progress-every", str(max(1, int(c["progressEvery"]))),
            "--watchdog-seconds", "25", "--generation-seconds", "90", "--heartbeat-seconds", "5",
        ]
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        core._proc = subprocess.Popen(
            cmd, cwd=core.ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=flags,
        )
        core.write_json(core.STATUS, {
            **core.base_status(), "state": "running", "pid": core._proc.pid,
            "maxGenerations": c["generations"], "message": "Démarrage v5 non-répétitif",
        })
        threading.Thread(target=core.reader, args=(core._proc,), daemon=True).start()
        return True, f"Solveur v5 lancé (PID {core._proc.pid})."


core.start_solver = start_solver_v5

HTML = core.HTML
HTML = HTML.replace("Recherche autonome locale · OMSim.", "Recherche v5 non-répétitive · OMSim · audit de diversité.")
HTML = HTML.replace("Disponible à la fin du run.", "Top mécaniquement distinct · mis à jour à chaque checkpoint.")
HTML = re.sub(
    r'(<input id="workers"[^>]*)(>)',
    lambda m: re.sub(r'\smax="\d+"', '', m.group(1)) + ' max="8"' + m.group(2),
    HTML,
    count=1,
)
HTML = HTML.replace("loadCfg();refresh();setInterval(refresh,1000);", "loadCfg();(async function poll(){for(;;){await refresh();await new Promise(r=>setTimeout(r,1000));}})();")
HTML = HTML.replace("catch(e){err('Refresh: '+e.message)}", "catch(e){console.warn('Refresh:',e.message)}")


class Handler(core.Handler):
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/":
            return self.send(HTML.encode(), "text/html; charset=utf-8")
        if p == "/api/status":
            return self.js(status_v5())
        if p.startswith("/download/top-") and p.endswith(".solution"):
            m = re.match(r"/download/top-(\d+)\.solution$", p)
            if not m:
                return self.js({"message": "Solution indisponible"}, 404)
            rank = int(m.group(1))
            f = core.WORK / f"top-{rank}.solution"
            if not f.exists():
                return self.js({"message": "Solution indisponible"}, 404)
            return self.send(
                f.read_bytes(), "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="aqueous-v5-top-{rank}.solution"'},
            )
        return super().do_GET()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    safe_config()
    core.status()
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    url = f"http://{a.host}:{a.port}/"
    print(f"OM Agent dashboard v5 non-repeating: {url}", flush=True)
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
