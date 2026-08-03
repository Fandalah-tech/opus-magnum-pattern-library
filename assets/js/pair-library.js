(() => {
  const DB_NAME = "opus-solution-inspector";
  const DB_VERSION = 1;
  const STORE = "pairs";

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: "id" });
          store.createIndex("updatedAt", "updatedAt");
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function transact(mode, operation) {
    const db = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        const request = operation(store);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        tx.onerror = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  }

  const api = {
    async list() {
      const records = await transact("readonly", (store) => store.getAll());
      return records.sort((a, b) => b.updatedAt - a.updatedAt);
    },

    async get(id) {
      return transact("readonly", (store) => store.get(id));
    },

    async save(puzzleFile, solutionFile, label = null) {
      if (!puzzleFile || !solutionFile) return null;
      const id = `${puzzleFile.name}::${solutionFile.name}`;
      const existing = await this.get(id);
      const record = {
        id,
        label: label || existing?.label || solutionFile.name.replace(/\.solution$/i, ""),
        puzzleName: puzzleFile.name,
        solutionName: solutionFile.name,
        puzzleType: puzzleFile.type || "application/octet-stream",
        solutionType: solutionFile.type || "application/octet-stream",
        puzzleBlob: puzzleFile,
        solutionBlob: solutionFile,
        createdAt: existing?.createdAt || Date.now(),
        updatedAt: Date.now(),
      };
      await transact("readwrite", (store) => store.put(record));
      return record;
    },

    async remove(id) {
      await transact("readwrite", (store) => store.delete(id));
    },

    async rename(id, label) {
      const record = await this.get(id);
      if (!record) return null;
      record.label = label;
      record.updatedAt = Date.now();
      await transact("readwrite", (store) => store.put(record));
      return record;
    },

    toFiles(record) {
      return {
        puzzle: new File([record.puzzleBlob], record.puzzleName, { type: record.puzzleType }),
        solution: new File([record.solutionBlob], record.solutionName, { type: record.solutionType }),
      };
    },
  };

  window.OpusPairLibrary = api;
})();
