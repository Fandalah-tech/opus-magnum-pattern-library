(() => {
  const REPO = 'Fandalah-tech/opus-magnum-pattern-library';
  const BRANCH = 'feature/disjoint-solver-readiness';
  const WORKFLOW = 'om-local-worker.yml';
  const POLL_MS = 15000;
  const nodes = { badge:document.querySelector('#monitor-badge'), stage:document.querySelector('#monitor-stage'), elapsed:document.querySelector('#monitor-elapsed'), depth:document.querySelector('#monitor-depth'), visited:document.querySelector('#monitor-visited'), expanded:document.querySelector('#monitor-expanded'), score:document.querySelector('#monitor-score'), progress:document.querySelector('#monitor-progress-bar'), log:document.querySelector('#monitor-log'), updated:document.querySelector('#monitor-updated'), run:document.querySelector('#monitor-run') };
  if (!nodes.badge) return;
  const num=v=>Number.isFinite(Number(v))?Number(v).toLocaleString('fr-CA'):'—';
  const duration=s=>{s=Number(s);if(!Number.isFinite(s)||s<0)return'—';const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=Math.floor(s%60);return h?`${h} h ${String(m).padStart(2,'0')} min`:`${m} min ${String(x).padStart(2,'0')} s`};
  const badge=(t,k='')=>{nodes.badge.textContent=t;nodes.badge.className=`monitor-badge ${k}`.trim()};
  const raw=async p=>{const r=await fetch(`https://raw.githubusercontent.com/${REPO}/${BRANCH}/${p}?t=${Date.now()}`,{cache:'no-store'});return r.ok?r.json():null};
  const api=async u=>{const r=await fetch(u,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw Error(`GitHub ${r.status}`);return r.json()};
  function apply(live){
    const stopped=['stopped','completed','success','finished'].includes(String(live.status||'').toLowerCase());
    nodes.stage.textContent=stopped?'Terminée':(live.stage||'Inconnu');
    nodes.elapsed.textContent=duration(live.elapsedSeconds??live.elapsed_seconds??live.timeLimitSeconds);
    nodes.depth.textContent=num(live.depth);nodes.visited.textContent=num(live.visitedStates??live.visited_states);nodes.expanded.textContent=num(live.expandedStates??live.expanded_states);nodes.score.textContent=num(live.bestScore??live.best_score);
    const d=Number(live.depth),m=Number(live.maxDepth??live.max_depth);nodes.progress.style.width=`${Number.isFinite(d)&&Number.isFinite(m)&&m>0?Math.min(100,Math.max(0,d/m*100)):0}%`;
    if(stopped)badge(live.found?'Solution trouvée':'Terminée','success');else if(['failed','error'].includes(String(live.status||'').toLowerCase()))badge('Intervention','failure');else badge('En cours','running');
    nodes.log.textContent=[live.message,Number.isFinite(d)?`Profondeur ${d}${Number.isFinite(m)?` / ${m}`:''}`:null,live.stoppedReason?`Arrêt : ${live.stoppedReason}`:null,live.found===false?'Aucune solution complète trouvée.':null].filter(Boolean).join('\n');
  }
  async function worker(){try{const x=await api(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=${encodeURIComponent(BRANCH)}&per_page=1`),r=x.workflow_runs?.[0];if(!r)return;nodes.run.textContent=`Run #${r.run_number}`;nodes.run.href=r.html_url;const s=r.status==='queued'?'Worker en file':r.status==='in_progress'?'Worker actif':r.conclusion==='success'?'Worker terminé':`Worker : ${r.conclusion||r.status}`;nodes.updated.textContent=`${s} · actualisé ${new Date().toLocaleTimeString('fr-CA')}`}catch{nodes.updated.textContent=`Campagne chargée · actualisé ${new Date().toLocaleTimeString('fr-CA')}`}}
  async function refresh(){try{const live=await raw('reports/live-search-status.json');if(live)apply(live);else{badge('Indisponible','failure');nodes.log.textContent='Aucun rapport de campagne publié.'}await worker()}catch(e){badge('Indisponible','failure');nodes.log.textContent=`Impossible de lire l’état de la recherche : ${e.message}`;nodes.updated.textContent=`Nouvel essai dans ${POLL_MS/1000} s`}}
  refresh();setInterval(refresh,POLL_MS);
})();
