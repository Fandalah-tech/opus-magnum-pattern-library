(() => {
  const body = document.body;
  const page = body.dataset.product || 'project';
  const bilingual = body.dataset.bilingual === 'true';
  const embedded = new URLSearchParams(window.location.search).has('embedded');
  const oldHeader = document.querySelector('body > header');

  if (embedded) {
    if (oldHeader) oldHeader.remove();
    body.classList.add('is-embedded');
    return;
  }

  const labels = {
    project: 'Carte du projet',
    codex: 'Codex',
    laboratory: 'Laboratoire',
    solver: 'Solver Lab',
    monitor: 'Recherche en direct'
  };
  const links = [
    ['project', 'project.html', 'Projet'],
    ['codex', 'index.html', 'Codex'],
    ['laboratory', 'inspector.html', 'Laboratoire'],
    ['solver', 'solver-lab.html', 'Solver']
  ];
  const header = document.createElement('header');
  header.className = 'site-shell';
  header.innerHTML = `
    <a class="site-shell__brand" href="project.html" aria-label="Carte du projet">
      <span class="site-shell__mark">OM</span>
      <span><small>OPUS MAGNUM CODEX / OMSIM</small><strong>${labels[page] || labels.project}</strong></span>
    </a>
    <nav class="site-shell__nav" aria-label="Navigation principale">
      ${links.map(([id, href, label]) => `<a href="${href}"${page === id || (page === 'monitor' && id === 'solver') ? ' class="active"' : ''}>${label}</a>`).join('')}
      ${page === 'solver' || page === 'monitor' ? '<a href="research-monitor.html"' + (page === 'monitor' ? ' class="active"' : '') + '>Recherche en direct</a>' : ''}
      <label class="site-shell__language" data-disabled="${bilingual ? 'false' : 'true'}" title="${bilingual ? 'Langue de l’interface' : 'Traduction complète à venir'}">
        <span aria-hidden="true">🌐</span>
        <select id="site-locale-select" aria-label="Langue" ${bilingual ? '' : 'disabled'}>
          <option value="fr">FR</option>
          <option value="en">EN</option>
        </select>
      </label>
    </nav>`;
  if (oldHeader) oldHeader.replaceWith(header); else body.prepend(header);

  const shared = document.getElementById('site-locale-select');
  const legacy = document.getElementById('locale-select');
  const stored = localStorage.getItem('om-locale') || document.documentElement.lang?.slice(0, 2) || 'fr';
  if (shared) shared.value = stored === 'en' ? 'en' : 'fr';
  if (legacy && shared) {
    legacy.hidden = true;
    shared.value = legacy.value || shared.value;
    shared.addEventListener('change', () => {
      legacy.value = shared.value;
      localStorage.setItem('om-locale', shared.value);
      legacy.dispatchEvent(new Event('change', { bubbles: true }));
    });
    legacy.addEventListener('change', () => { shared.value = legacy.value; });
  }
})();
