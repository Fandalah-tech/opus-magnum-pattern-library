from __future__ import annotations

import argparse
import re
import threading
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer

import tools.om_agent_dashboard_v2 as core
import tools.om_agent_dashboard_v3 as v3


# Hard-cap the local search to the Cloud Run capacity we actually want to use.
_original_config = core.config


def safe_config() -> dict:
    c = _original_config()
    workers = max(1, min(12, int(c.get("workers", 12))))
    if c.get("workers") != workers:
        c["workers"] = workers
        core.write_json(core.CONFIG, c)
    return c


core.config = safe_config
core.DEFAULT_CONFIG["workers"] = min(12, int(core.DEFAULT_CONFIG.get("workers", 12)))

_original_start = core.start_solver


def safe_start_solver() -> tuple[bool, str]:
    c = safe_config()
    if int(c.get("workers", 12)) > 12:
        c["workers"] = 12
        core.write_json(core.CONFIG, c)
    return _original_start()


core.start_solver = safe_start_solver

_original_parse_line = core.parse_line


def parse_line_v4(line: str) -> None:
    m = re.search(
        r"HEARTBEAT generation=(\d+)/(\d+) tested=(\d+)/(\d+) pending=(\d+) idle=([0-9.]+)s timeouts=(\d+)",
        line,
    )
    if m:
        g, mg, tested, total, pending, idle, timeouts = m.groups()
        core.patch_status(
            generation=int(g),
            maxGenerations=int(mg),
            generationTested=int(tested),
            generationTotal=int(total),
            pending=int(pending),
            idleSeconds=float(idle),
            generationTimeouts=int(timeouts),
            message=f"Actif · {pending} en attente · dernier résultat il y a {idle}s",
        )
        return
    m = re.search(
        r"WATCHDOG generation=(\d+)/(\d+) no-result-for=([0-9.]+)s abandoning=(\d+)",
        line,
    )
    if m:
        g, mg, idle, abandoned = m.groups()
        core.patch_status(
            generation=int(g),
            maxGenerations=int(mg),
            message=f"Watchdog · {abandoned} validations abandonnées après {idle}s · passage à la suite",
        )
        return
    m = re.search(
        r"CHECKPOINT generation=(\d+) best=(\d+) elites=(\d+) valid=(\d+) timeouts=(\d+)",
        line,
    )
    if m:
        g, best, elites, valid, timeouts = map(int, m.groups())
        core.patch_status(
            generation=g,
            bestCycles=best,
            distinctElites=elites,
            generationValid=valid,
            generationTimeouts=timeouts,
            message=f"Checkpoint G{g} · {elites} élites distinctes · {timeouts} timeouts",
        )
        return
    _original_parse_line(line)


core.parse_line = parse_line_v4


HTML = v3.HTML
HTML = re.sub(
    r'(<input id="workers"[^>]*)(>)',
    lambda m: re.sub(r'\smax="\d+"', '', m.group(1)) + ' max="12"' + m.group(2),
    HTML,
    count=1,
)
HTML = HTML.replace(
    "Recherche autonome locale · OMSim.",
    "Recherche autonome locale · OMSim · mode unattended avec watchdog.",
)
HTML = HTML.replace(
    "Les 3 élites apparaissent dès la fin de chaque génération.",
    "Top 3 distinct sémantiquement · disponible dès chaque génération terminée.",
)


class Handler(v3.Handler):
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/":
            return self.send(HTML.encode(), "text/html; charset=utf-8")
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
    print(f"OM Agent dashboard v4 unattended: {url}", flush=True)
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
