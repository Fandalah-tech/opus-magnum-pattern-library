from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime")) / "OpusMagnumAgent" / "dashboard"
RUNTIME.mkdir(parents=True, exist_ok=True)
STATUS = RUNTIME / "status.json"
CONFIG = RUNTIME / "config.json"
LOG = RUNTIME / "solver.log"
WORK = RUNTIME / "aqueous-evolution"
PUZZLE = RUNTIME / "aqueous-dagger.puzzle"
SEED = RUNTIME / "single27.solution"

DEFAULT_CONFIG = {
    "generations": 50,
    "elites": 3,
    "targetCycles": 26,
    "stagnation": 12,
    "workers": max(1, min(24, (os.cpu_count() or 8))),
    "progressEvery": 10,
    "validatorUrl": "https://opus-validator-6gflgqb25q-nn.a.run.app",
}

_lock = threading.RLock()
_proc: subprocess.Popen[str] | None = None
_reader_thread: threading.Thread | None = None
_started_at: float | None = None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)


def ensure_config() -> dict:
    cfg = read_json(CONFIG, DEFAULT_CONFIG)
    merged = {**DEFAULT_CONFIG, **cfg}
    atomic_json(CONFIG, merged)
    return merged


def initial_status() -> dict:
    cfg = ensure_config()
    return {
        "puzzle": "Aqueous Dagger",
        "state": "idle",
        "seedCycles": 27,
        "targetCycles": cfg["targetCycles"],
        "generation": 0,
        "maxGenerations": cfg["generations"],
        "generationTested": 0,
        "generationTotal": 0,
        "generationValid": 0,
        "tested": 0,
        "valid": 0,
        "bestCycles": 27,
        "bestMutation": "seed",
        "topSolutions": [],
        "history": [{"generation": 0, "bestCycles": 27, "tested": 0, "valid": 1}],
        "startedAt": None,
        "updatedAt": utcnow(),
        "pid": None,
        "message": "Prêt",
    }


def get_status() -> dict:
    if not STATUS.exists():
        atomic_json(STATUS, initial_status())
    s = read_json(STATUS, initial_status())
    with _lock:
        p = _proc
    if p is not None and p.poll() is None:
        s["pid"] = p.pid
        if s.get("state") not in {"paused", "stopping"}:
            s["state"] = "running"
    elif s.get("state") in {"running", "paused", "stopping"}:
        s["state"] = "idle"
        s["pid"] = None
    return s


def save_status(**changes) -> None:
    with _lock:
        s = get_status()
        s.update(changes)
        s["updatedAt"] = utcnow()
        atomic_json(STATUS, s)


def materialize() -> None:
    pairs = [
        (ROOT / "fixtures/weeklies2026/aqueous-dagger.puzzle.b64", PUZZLE),
        (ROOT / "fixtures/weeklies2026/aqueous-dagger-27c-single-reference.solution.b64", SEED),
    ]
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(src.read_text(encoding="utf-8").strip()))


def refresh_top() -> list[dict]:
    result_file = WORK / "results.json"
    tops: list[dict] = []
    if result_file.exists():
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            for rank, item in enumerate((data.get("top") or [])[:3], 1):
                metrics = item.get("metrics") or {}
                f = WORK / f"top-{rank}.solution"
                if f.exists():
                    tops.append({
                        "rank": rank,
                        "cycles": metrics.get("cycles"),
                        "cost": metrics.get("cost"),
                        "area": metrics.get("area"),
                        "instructions": metrics.get("instructions"),
                        "mutation": item.get("kind") or "candidate",
                        "generation": item.get("generation", 0),
                        "downloadUrl": f"/download/top-{rank}.solution",
                    })
        except Exception:
            pass
    return tops


def parse_solver_line(line: str) -> None:
    s = get_status()
    m = re.search(r"GENERATION (\d+)/(\d+) candidates=(\d+) parents=(\d+)", line)
    if m:
        gen, maxg, total, parents = map(int, m.groups())
        save_status(generation=gen, maxGenerations=maxg, generationTested=0,
                    generationTotal=total, generationValid=0,
                    message=f"Génération {gen}/{maxg} · {parents} élites")
        return
    m = re.search(r"PROGRESS generation=(\d+)/(\d+) tested=(\d+)/(\d+) cumulative=(\d+) valid=(\d+) best=(\d+)", line)
    if m:
        gen, maxg, gt, total, tested, gv, best = map(int, m.groups())
        save_status(generation=gen, maxGenerations=maxg, generationTested=gt,
                    generationTotal=total, generationValid=gv, tested=tested,
                    bestCycles=best, message=f"Recherche · génération {gen}/{maxg}")
        return
    if line.startswith("NEW GLOBAL BEST"):
        try:
            payload = json.loads(line.split("NEW GLOBAL BEST", 1)[1].strip())
            metrics = payload.get("metrics") or {}
            save_status(bestCycles=metrics.get("cycles", s.get("bestCycles", 27)),
                        bestMutation=payload.get("kind") or "candidate",
                        message="Nouveau meilleur trouvé")
        except Exception:
            pass
        return
    m = re.search(r"TARGET REACHED: (\d+)c in generation (\d+)", line)
    if m:
        save_status(state="target_reached", bestCycles=int(m.group(1)), generation=int(m.group(2)),
                    message="Cible atteinte")
    elif line.startswith("STOP: stagnation"):
        save_status(state="stagnated", message=line)


def reader_loop(proc: subprocess.Popen[str]) -> None:
    global _proc
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            log.write(f"{utcnow()} {line}\n")
            log.flush()
            parse_solver_line(line)
    code = proc.wait()
    tops = refresh_top()
    s = get_status()
    final_state = s.get("state")
    if final_state not in {"target_reached", "stagnated"}:
        final_state = "completed" if code == 0 else "failed"
    save_status(state=final_state, pid=None, topSolutions=tops,
                message=("Recherche terminée" if code == 0 else f"Échec solveur (code {code})"))
    with _lock:
        if _proc is proc:
            _proc = None


def start_solver() -> tuple[bool, str]:
    global _proc, _reader_thread, _started_at
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return False, "Le solveur est déjà en cours."
        cfg = ensure_config()
        materialize()
        if WORK.exists():
            shutil.rmtree(WORK)
        cmd = [
            sys.executable, "tools/run_aqueous_evolution.py",
            "--validator-url", str(cfg["validatorUrl"]),
            "--puzzle", str(PUZZLE),
            "--seed", str(SEED),
            "--work", str(WORK),
            "--generations", str(max(1, int(cfg["generations"]))),
            "--elites", str(max(1, int(cfg["elites"]))),
            "--target-cycles", str(int(cfg["targetCycles"])),
            "--stagnation", str(max(0, int(cfg["stagnation"]))),
            "--workers", str(max(1, int(cfg["workers"]))),
            "--progress-every", str(max(1, int(cfg["progressEvery"]))),
        ]
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1,
                                 creationflags=flags)
        _started_at = time.time()
        atomic_json(STATUS, {
            **initial_status(), "state": "running", "pid": _proc.pid,
            "targetCycles": int(cfg["targetCycles"]),
            "maxGenerations": int(cfg["generations"]),
            "startedAt": utcnow(), "message": "Démarrage du solveur",
        })
        _reader_thread = threading.Thread(target=reader_loop, args=(_proc,), daemon=True)
        _reader_thread.start()
        return True, f"Solveur lancé (PID {_proc.pid})."


def suspend_resume(suspend: bool) -> tuple[bool, str]:
    with _lock:
        p = _proc
    if p is None or p.poll() is not None:
        return False, "Aucun solveur actif."
    try:
        if os.name == "nt":
            import ctypes
            access = 0x0800 | 0x0002
            handle = ctypes.windll.kernel32.OpenProcess(access, False, p.pid)
            if not handle:
                raise OSError("OpenProcess failed")
            fn = ctypes.windll.ntdll.NtSuspendProcess if suspend else ctypes.windll.ntdll.NtResumeProcess
            status = fn(handle)
            ctypes.windll.kernel32.CloseHandle(handle)
            if status != 0:
                raise OSError(f"NT status {status}")
        else:
            os.kill(p.pid, signal.SIGSTOP if suspend else signal.SIGCONT)
        save_status(state="paused" if suspend else "running",
                    message="Recherche en pause" if suspend else "Recherche reprise")
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def stop_solver() -> tuple[bool, str]:
    with _lock:
        p = _proc
    if p is None or p.poll() is not None:
        save_status(state="idle", pid=None, message="Arrêté")
        return False, "Aucun solveur actif."
    save_status(state="stopping", message="Arrêt en cours")
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            p.terminate()
        return True, "Arrêt demandé."
    except Exception as exc:
        return False, str(exc)


HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Opus Magnum Codex — OM Agent</title><style>
:root{color-scheme:dark;--bg:#080e1d;--p:#111b31;--p2:#0d1628;--line:#293958;--text:#f2f6ff;--muted:#8fa7d2;--blue:#59c8ff;--green:#50e6a3;--yellow:#ffd166;--red:#ff6e86}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#182b52 0,#080e1d 45%,#060a12 100%);color:var(--text);font:15px/1.45 Inter,Segoe UI,system-ui,sans-serif;min-height:100vh}.w{max-width:1180px;margin:auto;padding:26px 20px 50px}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;flex-wrap:wrap}.eye{font-size:12px;font-weight:800;letter-spacing:.15em;color:var(--blue)}h1{font-size:31px;margin:5px 0}.muted{color:var(--muted)}.badge{border:1px solid var(--line);padding:9px 14px;border-radius:99px;background:#101a2f;font-weight:800}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--yellow);margin-right:8px}.controls,.grid,.two{display:grid;gap:12px}.controls{grid-template-columns:repeat(6,1fr);margin:22px 0}.grid{grid-template-columns:repeat(4,1fr)}.two{grid-template-columns:1.15fr .85fr;margin-top:12px}.card{border:1px solid var(--line);background:linear-gradient(180deg,var(--p),var(--p2));border-radius:17px;padding:16px}.label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.big{font-size:30px;font-weight:850;margin-top:4px}.btn{border:1px solid #35507c;background:#12213c;color:#fff;border-radius:10px;padding:10px 13px;font-weight:750;cursor:pointer}.btn:hover{border-color:var(--blue)}.btn.good{border-color:#28795f}.btn.warn{border-color:#8d7431}.btn.bad{border-color:#83384a}input{width:100%;margin-top:5px;padding:9px;border-radius:9px;border:1px solid var(--line);background:#091225;color:white}.bar{height:14px;border:1px solid var(--line);border-radius:99px;background:#07101f;overflow:hidden;margin-top:12px}.fill{height:100%;background:linear-gradient(90deg,#52b9ff,#60e4bd);width:0;transition:width .25s}.section{font-size:17px;font-weight:800;margin-bottom:12px}.tops{display:grid;gap:9px}.sol{display:grid;grid-template-columns:45px 75px 1fr auto;gap:12px;align-items:center;padding:11px;border-radius:12px;border:1px solid var(--line);background:#0b1426}.rank{font-weight:850;color:var(--blue)}.metrics{color:var(--muted);font-size:13px}.dl{display:inline-block;border:1px solid #337cb0;border-radius:9px;padding:7px 10px;color:var(--blue);text-decoration:none;font-weight:700}.history{display:flex;gap:8px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:10px;padding:8px 10px}.log{height:190px;overflow:auto;background:#070d18;border:1px solid var(--line);border-radius:10px;padding:10px;font:12px/1.4 Consolas,monospace;white-space:pre-wrap;color:#b8c7e6}@media(max-width:850px){.controls{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}@media(max-width:500px){.controls,.grid{grid-template-columns:1fr 1fr}.sol{grid-template-columns:35px 60px 1fr}.sol .dl{grid-column:1/-1;text-align:center}}
</style></head><body><div class="w"><div class="top"><div><div class="eye">OPUS MAGNUM CODEX · OM AGENT</div><h1>Aqueous Dagger — Local Solver</h1><div class="muted">Recherche autonome locale · OMSim · aucun cache GitHub.</div></div><div class="badge"><span class="dot" id="dot"></span><span id="state">CHARGEMENT</span></div></div>
<div class="controls"><div class="card"><div class="label">Générations</div><input id="generations" type="number" min="1" max="10000"></div><div class="card"><div class="label">Élites</div><input id="elites" type="number" min="1" max="8"></div><div class="card"><div class="label">Stagnation</div><input id="stagnation" type="number" min="0" max="1000"></div><div class="card"><div class="label">Workers</div><input id="workers" type="number" min="1" max="128"></div><button class="btn good" onclick="start()">▶ Start</button><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px"><button class="btn warn" onclick="pause()">⏸ Pause</button><button class="btn bad" onclick="stop()">■ Stop</button></div></div>
<div class="grid"><div class="card"><div class="label">Meilleur</div><div class="big"><span id="best">27</span>c</div><div class="muted" id="mutation">seed</div></div><div class="card"><div class="label">Cible</div><div class="big"><span id="target">26</span>c</div><div class="muted">arrêt automatique</div></div><div class="card"><div class="label">Testés total</div><div class="big" id="tested">0</div><div class="muted"><span id="valid">0</span> valides</div></div><div class="card"><div class="label">Génération</div><div class="big"><span id="gen">0</span>/<span id="maxgen">0</span></div><div class="muted" id="msg">Prêt</div></div></div>
<div class="card" style="margin-top:12px"><div class="section">Progression de la génération actuelle</div><div class="bar"><div class="fill" id="fill"></div></div><div class="muted" style="margin-top:8px"><span id="gp">0 / 0</span> · actualisation locale toutes les 1 s</div></div>
<div class="two"><div class="card"><div class="section">Top 3 solutions</div><div class="tops" id="tops"><div class="muted">Aucune solution publiée pour le moment.</div></div></div><div class="card"><div class="section">Historique</div><div class="history" id="history"></div><div class="muted" style="margin-top:13px" id="updated">—</div></div></div>
<div class="card" style="margin-top:12px"><div class="section">Journal solveur</div><div class="log" id="log"></div></div></div><script>
const $=id=>document.getElementById(id);let first=true;async function api(path,opt){const r=await fetch(path,{cache:'no-store',...(opt||{})});if(!r.ok)throw new Error(await r.text());return r.headers.get('content-type')?.includes('json')?r.json():r.text()}async function cfg(){const c=await api('/api/config');for(const k of ['generations','elites','stagnation','workers'])$(k).value=c[k]}async function saveCfg(){const body={};for(const k of ['generations','elites','stagnation','workers'])body[k]=Number($(k).value);await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}async function start(){await saveCfg();await api('/api/start',{method:'POST'});refresh()}async function pause(){const s=(await api('/api/status')).state;await api(s==='paused'?'/api/resume':'/api/pause',{method:'POST'});refresh()}async function stop(){await api('/api/stop',{method:'POST'});refresh()}function state(s){const m={running:['EN COURS','#ffd166'],paused:['PAUSE','#59c8ff'],completed:['TERMINÉ','#50e6a3'],target_reached:['CIBLE ATTEINTE','#50e6a3'],stagnated:['STAGNATION','#ffd166'],failed:['ÉCHEC','#ff6e86'],idle:['PRÊT','#8fa7d2'],stopping:['ARRÊT…','#ff6e86']};const x=m[s]||[String(s).toUpperCase(),'#8fa7d2'];$('state').textContent=x[0];$('dot').style.background=x[1]}async function refresh(){try{const s=await api('/api/status');state(s.state);$('best').textContent=s.bestCycles??'—';$('target').textContent=s.targetCycles??26;$('tested').textContent=s.tested??0;$('valid').textContent=s.valid??0;$('gen').textContent=s.generation??0;$('maxgen').textContent=s.maxGenerations??0;$('mutation').textContent=s.bestMutation||'seed';$('msg').textContent=s.message||'—';const t=s.generationTotal||0,g=s.generationTested||0;$('gp').textContent=`${g} / ${t}`;$('fill').style.width=(t?Math.min(100,100*g/t):0)+'%';$('updated').textContent='Dernière mise à jour : '+(s.updatedAt?new Date(s.updatedAt).toLocaleString('fr-CA'):'—');const tops=s.topSolutions||[];$('tops').innerHTML=tops.length?tops.map(x=>`<div class="sol"><div class="rank">#${x.rank}</div><div><b>${x.cycles}c</b></div><div><div>${x.mutation||'candidate'} · G${x.generation||0}</div><div class="metrics">${x.cost??'—'}G · A${x.area??'—'} · ${x.instructions??'—'}i</div></div><a class="dl" href="${x.downloadUrl}">Télécharger</a></div>`).join(''):'<div class="muted">Top 3 disponible dès la fin du run.</div>';$('history').innerHTML=(s.history||[]).map(x=>`<div class="chip">G${x.generation} · <b>${x.bestCycles}c</b></div>`).join('');const l=await api('/api/log');$('log').textContent=l;$('log').scrollTop=$('log').scrollHeight}catch(e){$('state').textContent='ERREUR LOCALE'}}if(first){first=false;cfg()}refresh();setInterval(refresh,1000)
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = "OMAgentDashboard/0.1"

    def log_message(self, fmt, *args):
        return

    def send_bytes(self, data: bytes, content_type: str, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(data)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj: dict, status=200):
        self.send_bytes(json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8", status)

    def body_json(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self.send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/status":
            return self.send_json(get_status())
        if path == "/api/config":
            return self.send_json(ensure_config())
        if path == "/api/log":
            text = ""
            if LOG.exists():
                lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
                text = "\n".join(lines)
            return self.send_bytes(text.encode("utf-8"), "text/plain; charset=utf-8")
        if path.startswith("/download/top-") and path.endswith(".solution"):
            name = Path(path).name
            file = WORK / name
            if not file.exists():
                return self.send_json({"error": "solution unavailable"}, 404)
            return self.send_bytes(file.read_bytes(), "application/octet-stream", extra={"Content-Disposition": f'attachment; filename="{name}"'})
        return self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/config":
            incoming = self.body_json()
            cfg = ensure_config()
            for key in ("generations", "elites", "stagnation", "workers", "progressEvery", "targetCycles"):
                if key in incoming:
                    cfg[key] = int(incoming[key])
            if "validatorUrl" in incoming:
                cfg["validatorUrl"] = str(incoming["validatorUrl"])
            atomic_json(CONFIG, cfg)
            return self.send_json(cfg)
        if path == "/api/start":
            ok, msg = start_solver(); return self.send_json({"ok": ok, "message": msg}, 200 if ok else 409)
        if path == "/api/pause":
            ok, msg = suspend_resume(True); return self.send_json({"ok": ok, "message": msg}, 200 if ok else 409)
        if path == "/api/resume":
            ok, msg = suspend_resume(False); return self.send_json({"ok": ok, "message": msg}, 200 if ok else 409)
        if path == "/api/stop":
            ok, msg = stop_solver(); return self.send_json({"ok": ok, "message": msg}, 200)
        return self.send_json({"error": "not found"}, 404)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    ensure_config()
    if not STATUS.exists():
        atomic_json(STATUS, initial_status())
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"OM Agent dashboard: {url}", flush=True)
    if args.open:
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
