(() => {
  const library = window.OpusPairLibrary;
  const app = window.OpusViewerApp;
  if (!library || !app) return;

  const select = document.querySelector('#viewer-saved-pair');
  const openButton = document.querySelector('#viewer-open-pair');
  const status = document.querySelector('#viewer-status');
  if (!select || !openButton) return;

  function setBusy(busy) {
    select.disabled = busy;
    openButton.disabled = busy || !select.value;
  }

  async function refresh(preferredId = null) {
    const records = await library.list();
    const requested = preferredId || select.value;
    select.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = records.length ? 'Choose a local pair…' : 'No local pair saved yet';
    select.append(empty);
    for (const record of records) {
      const option = document.createElement('option');
      option.value = record.id;
      option.textContent = `${record.label} — ${record.puzzleName}`;
      select.append(option);
    }
    if (records.some(record => record.id === requested)) select.value = requested;
    openButton.disabled = !select.value;
    return records;
  }

  async function openPair(id = select.value) {
    if (!id) return;
    setBusy(true);
    try {
      const record = await library.get(id);
      if (!record) throw new Error('Saved pair not found');
      const files = library.toFiles(record);
      select.value = record.id;
      await app.analyzeFiles(files.puzzle, files.solution);
      const url = new URL(location.href);
      url.searchParams.delete('fixture');
      url.searchParams.delete('demo');
      url.searchParams.set('pair', record.id);
      history.replaceState(null, '', url);
    } finally {
      setBusy(false);
    }
  }

  select.addEventListener('change', () => { openButton.disabled = !select.value; });
  select.addEventListener('dblclick', () => openPair());
  openButton.addEventListener('click', () => openPair());

  (async () => {
    try {
      const requested = new URLSearchParams(location.search).get('pair');
      const records = await refresh(requested);
      if (requested && records.some(record => record.id === requested)) await openPair(requested);
    } catch (error) {
      console.error(error);
      status.textContent = `Local library failed: ${error.message}`;
    }
  })();
})();
