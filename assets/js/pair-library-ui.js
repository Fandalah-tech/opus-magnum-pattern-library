(() => {
  const library = window.OpusPairLibrary;
  const i18n = window.OpusI18n;
  if (!library || !i18n) return;

  const puzzleInput = document.querySelector('#puzzle-file');
  const solutionInput = document.querySelector('#solution-file');
  const select = document.querySelector('#saved-pair-select');
  const loadButton = document.querySelector('#load-pair-button');
  const renameButton = document.querySelector('#rename-pair-button');
  const deleteButton = document.querySelector('#delete-pair-button');
  const status = document.querySelector('#status');
  const t = (key) => i18n.t(key);

  function setFile(input, file) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function updateButtons() {
    const selected = Boolean(select.value);
    loadButton.disabled = !selected;
    renameButton.disabled = !selected;
    deleteButton.disabled = !selected;
  }

  async function refresh(preferredId = null) {
    try {
      const records = await library.list();
      const current = preferredId || select.value;
      select.innerHTML = '';
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = t('library.empty');
      select.appendChild(empty);
      for (const record of records) {
        const option = document.createElement('option');
        option.value = record.id;
        option.textContent = `${record.label} — ${record.puzzleName}`;
        select.appendChild(option);
      }
      if (records.some((record) => record.id === current)) select.value = current;
      updateButtons();
    } catch (error) {
      console.error(error);
      status.textContent = t('library.storageError');
    }
  }

  async function saveCurrentPair() {
    const puzzle = puzzleInput.files[0];
    const solution = solutionInput.files[0];
    if (!puzzle || !solution) return;
    try {
      const record = await library.save(puzzle, solution);
      await refresh(record.id);
      status.textContent = t('library.saved');
    } catch (error) {
      console.error(error);
      status.textContent = t('library.storageError');
    }
  }

  async function loadSelected() {
    if (!select.value) return;
    try {
      const record = await library.get(select.value);
      if (!record) return refresh();
      const files = library.toFiles(record);
      setFile(puzzleInput, files.puzzle);
      setFile(solutionInput, files.solution);
      status.textContent = t('library.loaded');
    } catch (error) {
      console.error(error);
      status.textContent = t('library.storageError');
    }
  }

  puzzleInput.addEventListener('change', saveCurrentPair);
  solutionInput.addEventListener('change', saveCurrentPair);
  select.addEventListener('change', updateButtons);
  loadButton.addEventListener('click', loadSelected);
  select.addEventListener('dblclick', loadSelected);

  renameButton.addEventListener('click', async () => {
    if (!select.value) return;
    const record = await library.get(select.value);
    if (!record) return;
    const label = window.prompt(t('library.renamePrompt'), record.label);
    if (!label?.trim()) return;
    await library.rename(record.id, label.trim());
    await refresh(record.id);
  });

  deleteButton.addEventListener('click', async () => {
    if (!select.value) return;
    await library.remove(select.value);
    await refresh();
    status.textContent = t('library.deleted');
  });

  window.addEventListener('opus:localechange', () => refresh(select.value));
  refresh();
})();
