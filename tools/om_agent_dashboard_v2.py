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
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime")) / "OpusMagnumAgent" / "dashboard-v2"
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
    "workers": max(1, min(24, os.cpu_count() or 8)),
    "progressEvery": 10,
    "validatorUrl": "https://opus-validator-6gflgqb25q-nn.a.run.app",
}

_lock = threading.RLock()
_proc: subprocess.Popen[str] | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def config() -> dict:
    c = {**DEFAULT_CONFIG, **read_json(CONFIG, DEFAULT_CONFIG)}
    write_json(CONFIG, c)
    return c


def base_status() -> dict:
    c = config()
    return {
        "state": "idle", "message": "Prêt", "pid": None,
        "seedCycles": 27, "targetCycles": c["targetCycles"],
        "generation": 0, "maxGenerations": c["generations"],
        "generationTested": 0, "generationTotal": 0,
        "generationValid": 0, "tested": 0, "valid": 0,
        "bestCycles": 27, "bestMutation": "seed",
        "topSolutions": [],
        "history": [{"generation": 0, "bestCycles": 27, "tested": 0, "valid": 1}],
        "updatedAt": now(),
    }


def status() -> dict:
    if not STATUS.exists():
        write_json(STATUS, base_status())
    s = read_json(STATUS, base_status())
    with _lock:
        p = _proc
    alive = p is not None and p.poll() is None
    s["processAlive"] = alive
    if alive:
        s["pid"] = p.pid
        if s.get("state") not in {"paused", "stopping"}:
            s["state"] = "running"
    elif s.get("state") in {"running", "paused", "stopping"}:
        s["state"] = "idle"
        s["pid"] = None
    return s


def patch_status(**changes) -> None:
    s = status()
    s.update(changes)
    s["updatedAt"] = now()
    write_json(STATUS, s)


def materialize() -> None:
    pairs = [
        (ROOT / "fixtures/weeklies2026/aqueous-dagger.puzzle.b64", PUZZLE),
        (ROOT / "fixtures/weeklies2026/aqueous-dagger-27c-single-reference.solution.b64", SEED),
    ]
    for src, dst in pairs:
        dst.write_bytes(base64.b64decode(src.read_text(encoding="utf-8").strip()))


def parse_line(line: str) -> None:
    m = re.search(r"GENERATION (\d+)/(\d+) candidates=(\d+) parents=(\d+)", line)
    if m:
        g, mg, total, parents = map(int, m.groups())
        patch_status(generation=g, maxGenerations=mg, generationTested=0,
                     generationTotal=total, generationValid=0,
                     message=f"Génération {g}/{mg} · {parents} élites")
        return
    m = re.search(r"PROGRESS generation=(\d+)/(\d+) tested=(\d+)/(\d+) cumulative=(\d+) valid=(\d+) best=(\d+)", line)
    if m:
        g, mg, gt, total, tested, gv, best = map(int, m.groups())
        s = status()
        history = list(s.get("history") or [])
        if not history or history[-1].get("generation") != g:
            history.append({"generation": g, "bestCycles": best, "tested": gt, "valid": gv})
        else:
            history[-1] = {"generation": g, "bestCycles": best, "tested": gt, "valid": gv}
        patch_status(generation=g, maxGenerations=mg, generationTested=gt,
                     generationTotal=total, generationValid=gv, tested=tested,
                     bestCycles=best, history=history[-50:],
                     message=f"Recherche · génération {g}/{mg}")
        return
    if line.startswith("NEW GLOBAL BEST"):
        try:
            d = json.loads(line.split("NEW GLOBAL BEST", 1)[1].strip())
            metrics = d.get("metrics") or {}
            patch_status(bestCycles=metrics.get("cycles", status().get("bestCycles", 27)),
                         bestMutation=d.get("kind") or "candidate",
                         message="Nouveau meilleur trouvé")
        except Exception:
            pass
        return
    m = re.search(r"TARGET REACHED: (\d+)c in generation (\d+)", line)
    if m:
        patch_status(state="target_reached", bestCycles=int(m.group(1)),
                     generation=int(m.group(2)), message="Cible atteinte")
    elif line.startswith("STOP: stagnation"):
        patch_status(state="stagnated", message=line)


def load_top() -> list[dict]:
    rp = WORK / "results.json"
    if not rp.exists():
        return []
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
        out = []
        for rank, item in enumerate((data.get("top") or [])[:3], 1):
            f = WORK / f"top-{rank}.solution"
            if not f.exists():
                continue
            m = item.get("metrics") or {}
            out.append({"rank": rank, "cycles": m.get("cycles"), "cost": m.get("cost"),
                        "area": m.get("area"), "instructions": m.get("instructions"),
                        "mutation": item.get("kind") or "candidate",
                        "generation": item.get("generation", 0),
                        "downloadUrl": f"/download/top-{rank}.solution"})
        return out
    except Exception:
        return []


def reader(proc: subprocess.Popen[str]) -> None:
    global _proc
    with LOG.open("a", encoding="utf-8") as log:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            log.write(f"{now()} {line}\n")
            log.flush()
            parse_line(line)
    code = proc.wait()
    s = status()
    final = s.get("state")
    if final not in {"target_reached", "stagnated"}:
        final = "completed" if code == 0 else "failed"
    patch_status(state=final, pid=None, topSolutions=load_top(),
                 message="Recherche terminée" if code == 0 else f"Échec solveur (code {code})")
    with _lock:
        if _proc is proc:
            _proc = None


def start_solver() -> tuple[bool, str]:
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return False, "Le solveur est déjà actif."
        c = config()
        materialize()
        if WORK.exists():
            shutil.rmtree(WORK)
        LOG.write_text("", encoding="utf-8")
        cmd = [sys.executable, "tools/run_aqueous_evolution.py",
               "--validator-url", str(c["validatorUrl"]),
               "--puzzle", str(PUZZLE), "--seed", str(SEED), "--work", str(WORK),
               "--generations", str(max(1, int(c["generations"]))),
               "--elites", str(max(1, int(c["elites"]))),
               "--target-cycles", str(int(c["targetCycles"])),
               "--stagnation", str(max(0, int(c["stagnation"]))),
               "--workers", str(max(1, int(c["workers"]))),
               "--progress-every", str(max(1, int(c["progressEvery"])))]
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        _proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1, creationflags=flags)
        write_json(STATUS, {**base_status(), "state": "running", "pid": _proc.pid,
                            "targetCycles": int(c["targetCycles"]),
                            "maxGenerations": int(c["generations"]),
                            "message": "Démarrage du solveur", "updatedAt": now()})
        threading.Thread(target=reader, args=(_proc,), daemon=True).start()
        return True, f"Solveur lancé (PID {_proc.pid})."


def pause_resume(pause: bool) -> tuple[bool, str]:
    with _lock:
        p = _proc
    if p is None or p.poll() is not None:
        return False, "Aucun solveur actif."
    try:
        if os.name == "nt":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x0800 | 0x0002, False, p.pid)
            if not handle:
                raise OSError("OpenProcess failed")
            fn = ctypes.windll.ntdll.NtSuspendProcess if pause else ctypes.windll.ntdll.NtResumeProcess
            rc = fn(handle)
            ctypes.windll.kernel32.CloseHandle(handle)
            if rc != 0:
                raise OSError(f"NT status {rc}")
        else:
            os.kill(p.pid, signal.SIGSTOP if pause else signal.SIGCONT)
        patch_status(state="paused" if pause else "running",
                     message="Recherche en pause" if pause else "Recherche reprise")
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def stop_solver() -> tuple[bool, str]:
    with _lock:
        p = _proc
    if p is None or p.poll() is not None:
        patch_status(state="idle", pid=None, message="Arrêté")
        return True, "Déjà arrêté."
    patch_status(state="stopping", message="Arrêt en cours")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.terminate()
    return True, "Arrêt demandé."


HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OM Agent</title><style>
:root{color-scheme:dark;--bg:#080e1d;--p:#111b31;--line:#293958;--text:#f2f6ff;--muted:#8fa7d2;--blue:#59c8ff;--green:#50e6a3;--yellow:#ffd166;--red:#ff6e86}*{box-sizing:border-box}body{margin:0;background:#080e1d;color:var(--text);font:15px/1.45 Segoe UI,system-ui,sans-serif}.w{max-width:1180px;margin:auto;padding:26px 20px}.top{display:flex;justify-content:space-between;align-items:flex-start}.eye{font-size:12px;font-weight:800;letter-spacing:.15em;color:var(--blue)}h1{font-size:31px;margin:5px 0}.muted{color:var(--muted)}.badge,.card{border:1px solid var(--line);background:var(--p);border-radius:16px}.badge{padding:9px 14px;font-weight:800}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--yellow);margin-right:8px}.controls,.grid,.two{display:grid;gap:12px}.controls{grid-template-columns:repeat(6,1fr);margin:22px 0}.grid{grid-template-columns:repeat(4,1fr)}.two{grid-template-columns:1.1fr .9fr;margin-top:12px}.card{padding:16px}.label{font-size:11px;text-transform:uppercase;color:var(--muted)}.big{font-size:30px;font-weight:850}.btn{border:1px solid #35507c;background:#12213c;color:white;border-radius:10px;padding:10px;font-weight:750;cursor:pointer}.btn:disabled{opacity:.4;cursor:not-allowed}.btn.good{border-color:#28795f}.btn.warn{border-color:#8d7431}.btn.bad{border-color:#83384a}input{width:100%;margin-top:5px;padding:9px;border-radius:9px;border:1px solid var(--line);background:#091225;color:white}.bar{height:14px;border:1px solid var(--line);border-radius:99px;background:#07101f;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#52b9ff,#60e4bd);width:0}.section{font-size:17px;font-weight:800;margin-bottom:12px}.alert{display:none;margin:12px 0;padding:12px;border:1px solid #83384a;background:#2a1220;border-radius:12px;color:#ffd4dc}.tops{display:grid;gap:8px}.sol{display:grid;grid-template-columns:40px 70px 1fr auto;gap:10px;align-items:center;border:1px solid var(--line);border-radius:10px;padding:10px}.dl{color:var(--blue)}.history{display:flex;gap:8px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:10px;padding:8px}.log{height:180px;overflow:auto;background:#060b14;border:1px solid var(--line);border-radius:10px;padding:10px;font:12px Consolas,monospace;white-space:pre-wrap}@media(max-width:850px){.controls{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}
</style></head><body><div class="w"><div class="top"><div><div class="eye">OPUS MAGNUM CODEX · OM AGENT</div><h1>Aqueous Dagger — Local Solver</h1><div class="muted">Recherche autonome locale · OMSim.</div></div><div class="badge"><span class="dot" id="dot"></span><span id="state">PRÊT</span></div></div><div id="alert" class="alert"></div>
<div class="controls"><div class="card"><div class="label">Générations</div><input id="generations" type="number" min="1"></div><div class="card"><div class="label">Élites</div><input id="elites" type="number" min="1" max="8"></div><div class="card"><div class="label">Stagnation</div><input id="stagnation" type="number" min="0"></div><div class="card"><div class="label">Workers</div><input id="workers" type="number" min="1"></div><button id="startBtn" class="btn good">▶ Start</button><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px"><button id="pauseBtn" class="btn warn">⏸ Pause</button><button id="stopBtn" class="btn bad">■ Stop</button></div></div>
<div class="grid"><div class="card"><div class="label">Meilleur</div><div class="big"><span id="best">27</span>c</div><div id="mutation" class="muted">seed</div></div><div class="card"><div class="label">Cible</div><div class="big"><span id="target">26</span>c</div></div><div class="card"><div class="label">Testés total</div><div class="big" id="tested">0</div><div class="muted"><span id="valid">0</span> valides</div></div><div class="card"><div class="label">Génération</div><div class="big"><span id="gen">0</span>/<span id="maxgen">0</span></div><div class="muted" id="msg">Prêt</div></div></div>
<div class="card" style="margin-top:12px"><div class="section">Progression</div><div class="bar"><div id="fill" class="fill"></div></div><div class="muted" style="margin-top:8px" id="gp">0 / 0</div></div>
<div class="two"><div class="card"><div class="section">Top 3 solutions</div><div id="tops" class="tops"></div></div><div class="card"><div class="section">Historique</div><div id="history" class="history"></div></div></div>
<div class="card" style="margin-top:12px"><div class="section">Journal solveur</div><div id="log" class="log"></div></div></div>
<script>
const E=id=>document.getElementById(id);
async function api(path,opt={}){const r=await fetch(path,{cache:'no-store',...opt});const text=await r.text();let data=text;try{data=JSON.parse(text)}catch{}if(!r.ok)throw new Error((data&&data.message)||text||('HTTP '+r.status));return data}
function err(x){const a=E('alert');a.textContent=String(x);a.style.display='block';setTimeout(()=>a.style.display='none',8000)}
async function loadCfg(){try{const c=await api('/api/config');for(const k of ['generations','elites','stagnation','workers'])E(k).value=c[k]}catch(e){err(e)}}
async function saveCfg(){const body={};for(const k of ['generations','elites','stagnation','workers'])body[k]=Number(E(k).value);return api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
async function doStart(){try{E('startBtn').disabled=true;await saveCfg();await api('/api/start',{method:'POST'});await refresh()}catch(e){err('Start: '+e.message)}finally{E('startBtn').disabled=false}}
async function doPause(){try{const s=await api('/api/status');await api(s.state==='paused'?'/api/resume':'/api/pause',{method:'POST'});await refresh()}catch(e){err('Pause/Reprise: '+e.message)}}
async function doStop(){try{await api('/api/stop',{method:'POST'});await refresh()}catch(e){err('Stop: '+e.message)}}
E('startBtn').addEventListener('click',doStart);E('pauseBtn').addEventListener('click',doPause);E('stopBtn').addEventListener('click',doStop);
function showState(s){const m={running:['EN COURS','#ffd166'],paused:['PAUSE','#59c8ff'],completed:['TERMINÉ','#50e6a3'],target_reached:['CIBLE ATTEINTE','#50e6a3'],stagnated:['STAGNATION','#ffd166'],failed:['ÉCHEC','#ff6e86'],idle:['PRÊT','#8fa7d2'],stopping:['ARRÊT…','#ff6e86']};const x=m[s]||[String(s).toUpperCase(),'#8fa7d2'];E('state').textContent=x[0];E('dot').style.background=x[1];E('startBtn').disabled=s==='running'||s==='paused'||s==='stopping';E('pauseBtn').disabled=!(s==='running'||s==='paused');E('stopBtn').disabled=!(s==='running'||s==='paused'||s==='stopping')}
async function refresh(){try{const s=await api('/api/status');showState(s.state);E('best').textContent=s.bestCycles??'—';E('target').textContent=s.targetCycles??26;E('tested').textContent=s.tested??0;E('valid').textContent=s.valid??0;E('gen').textContent=s.generation??0;E('maxgen').textContent=s.maxGenerations??0;E('mutation').textContent=s.bestMutation||'seed';E('msg').textContent=s.message||'—';const gt=s.generationTested||0,total=s.generationTotal||0;E('gp').textContent=`${gt} / ${total}`;E('fill').style.width=(total?Math.min(100,100*gt/total):0)+'%';const tops=s.topSolutions||[];E('tops').innerHTML=tops.length?tops.map(x=>`<div class="sol"><b>#${x.rank}</b><b>${x.cycles}c</b><span>${x.mutation} · G${x.generation} · ${x.cost??'—'}G · A${x.area??'—'}</span><a class="dl" href="${x.downloadUrl}">Télécharger</a></div>`).join(''):'<div class="muted">Disponible à la fin du run.</div>';E('history').innerHTML=(s.history||[]).map(x=>`<div class="chip">G${x.generation} · <b>${x.bestCycles}c</b></div>`).join('');E('log').textContent=await api('/api/log');E('log').scrollTop=E('log').scrollHeight}catch(e){err('Refresh: '+e.message)}}
loadCfg();refresh();setInterval(refresh,1000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def send(self, body: bytes, ctype: str, code=200, headers=None):
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def js(self, obj, code=200): self.send(json.dumps(obj).encode(), 'application/json; charset=utf-8', code)
    def body(self):
        n=int(self.headers.get('Content-Length','0') or 0); return json.loads(self.rfile.read(n).decode()) if n else {}
    def do_GET(self):
        p=urllib.parse.urlparse(self.path).path
        if p=='/': return self.send(HTML.encode(),'text/html; charset=utf-8')
        if p=='/api/status': return self.js(status())
        if p=='/api/config': return self.js(config())
        if p=='/api/log':
            text='\n'.join(LOG.read_text(encoding='utf-8',errors='replace').splitlines()[-150:]) if LOG.exists() else ''
            return self.send(text.encode(),'text/plain; charset=utf-8')
        if p.startswith('/download/top-') and p.endswith('.solution'):
            f=WORK/Path(p).name
            if not f.exists(): return self.js({'message':'Solution indisponible'},404)
            return self.send(f.read_bytes(),'application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{f.name}"'})
        self.js({'message':'Not found'},404)
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path
        try:
            if p=='/api/config':
                c=config(); inc=self.body()
                for k in ('generations','elites','stagnation','workers','progressEvery','targetCycles'):
                    if k in inc: c[k]=int(inc[k])
                write_json(CONFIG,c); return self.js(c)
            if p=='/api/start': ok,msg=start_solver(); return self.js({'ok':ok,'message':msg},200 if ok else 409)
            if p=='/api/pause': ok,msg=pause_resume(True); return self.js({'ok':ok,'message':msg},200 if ok else 409)
            if p=='/api/resume': ok,msg=pause_resume(False); return self.js({'ok':ok,'message':msg},200 if ok else 409)
            if p=='/api/stop': ok,msg=stop_solver(); return self.js({'ok':ok,'message':msg})
            return self.js({'message':'Not found'},404)
        except Exception as exc:
            return self.js({'ok':False,'message':f'{type(exc).__name__}: {exc}'},500)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=8765); ap.add_argument('--open',action='store_true'); a=ap.parse_args()
    config(); status(); server=ThreadingHTTPServer((a.host,a.port),Handler)
    url=f'http://{a.host}:{a.port}/'; print(f'OM Agent dashboard v2: {url}',flush=True)
    if a.open: threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0

if __name__=='__main__': raise SystemExit(main())
