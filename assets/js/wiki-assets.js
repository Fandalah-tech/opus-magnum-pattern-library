(() => {
  const API = 'https://opus-magnum.fandom.com/api.php';
  const WIKI = 'https://opus-magnum.fandom.com/wiki/';
  const CACHE_KEY = 'opus-codex-wiki-assets-v1';

  const references = {
    'Single Projection': [
      { query: 'Glyph of Projection', page: 'Glyphs', label: 'Glyph of Projection' },
      { query: 'single arm', page: 'Mechanisms', label: 'Arm' }
    ],
    'Double Projection': [
      { query: 'Glyph of Projection', page: 'Glyphs', label: 'Projection glyph' },
      { query: 'Quicksilver', page: 'Elements', label: 'Quicksilver' }
    ],
    'Shared Axis': [
      { query: 'single arm', page: 'Mechanisms', label: 'Arm' },
      { query: 'Piston arm', page: 'Mechanisms', label: 'Piston arm' }
    ],
    'Timed Handoff': [
      { query: 'single arm', page: 'Mechanisms', label: 'Arm' },
      { query: 'Glyph of Bonding', page: 'Glyphs', label: 'Bonding glyph' }
    ],
    'Loop Buffer': [
      { query: 'Track', page: 'Mechanisms', label: 'Track' },
      { query: 'single arm', page: 'Mechanisms', label: 'Arm' }
    ],
    'Mirror Assembler': [
      { query: 'Glyph of Bonding', page: 'Glyphs', label: 'Bonding glyph' },
      { query: 'single arm', page: 'Mechanisms', label: 'Arm' }
    ]
  };

  let cache = {};
  try { cache = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}'); } catch (_) {}

  async function searchFile(query) {
    if (cache[query]) return cache[query];
    const params = new URLSearchParams({
      action: 'query',
      format: 'json',
      origin: '*',
      generator: 'search',
      gsrnamespace: '6',
      gsrlimit: '8',
      gsrsearch: query,
      prop: 'imageinfo',
      iiprop: 'url',
      iiurlwidth: '180'
    });
    try {
      const response = await fetch(`${API}?${params}`);
      if (!response.ok) return null;
      const data = await response.json();
      const pages = Object.values(data?.query?.pages || {});
      const best = pages.find(page => page.imageinfo?.[0]?.thumburl || page.imageinfo?.[0]?.url);
      if (!best) return null;
      const info = best.imageinfo[0];
      const result = { url: info.thumburl || info.url, title: best.title.replace(/^File:/, '') };
      cache[query] = result;
      localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
      return result;
    } catch (_) {
      return null;
    }
  }

  async function buildReferenceStrip(patternName) {
    const items = references[patternName];
    if (!items) return null;
    const strip = document.createElement('div');
    strip.className = 'wiki-reference-strip';
    strip.setAttribute('aria-label', 'Game reference assets from the Opus Magnum Wiki');

    for (const item of items) {
      const asset = await searchFile(item.query);
      if (!asset) continue;
      const link = document.createElement('a');
      link.href = `${WIKI}${encodeURIComponent(item.page)}`;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.title = `${item.label} — Opus Magnum Wiki, CC BY-SA`;
      link.innerHTML = `<img src="${asset.url}" alt="${item.label}" loading="lazy"><span>${item.label}</span>`;
      strip.appendChild(link);
    }

    if (!strip.children.length) return null;
    const credit = document.createElement('small');
    credit.className = 'wiki-reference-credit';
    credit.textContent = 'Reference assets: Opus Magnum Wiki · CC BY-SA';
    strip.appendChild(credit);
    return strip;
  }

  async function enhanceCard(card) {
    if (card.dataset.wikiEnhanced) return;
    const name = card.querySelector('h3')?.textContent?.trim();
    if (!references[name]) return;
    card.dataset.wikiEnhanced = 'pending';
    const strip = await buildReferenceStrip(name);
    if (strip) card.querySelector('.card-visual')?.appendChild(strip);
    card.dataset.wikiEnhanced = 'true';
  }

  async function enhanceDialog() {
    const detail = document.querySelector('#pattern-detail');
    const name = detail?.querySelector('h2')?.textContent?.trim();
    const hero = detail?.querySelector('.detail-hero');
    if (!name || !hero || hero.dataset.wikiEnhanced || !references[name]) return;
    hero.dataset.wikiEnhanced = 'pending';
    const strip = await buildReferenceStrip(name);
    if (strip) hero.appendChild(strip);
    hero.dataset.wikiEnhanced = 'true';
  }

  function scan() {
    document.querySelectorAll('.pattern-card').forEach(enhanceCard);
    enhanceDialog();
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.body, { childList: true, subtree: true });
  scan();
})();
