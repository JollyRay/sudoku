function browserStorage() {
    try { return globalThis.localStorage ?? null; } catch { return null; }
}

export class LocalContext {
    constructor(room, username, {storage = browserStorage(), onChange = () => {}} = {}) {
        this.key = `sudoku-v2:${JSON.stringify([room, username])}`;
        this.storage = storage;
        this.onChange = onChange;
        this.generationId = undefined;
        this.notes = {};
        this.sprite = null;
        this.symbolSource = 'preset';
        this.persistenceError = '';
        try {
            const saved=JSON.parse(this.storage?.getItem(this.key) ?? 'null');
            this.symbolSource=saved?.symbolSource==='custom'?'custom':'preset';
        } catch { this.fail(); }
    }
    fail() {
        this.persistenceError = 'Браузер не смог сохранить настройки. После перезагрузки они могут потеряться.';
    }
    loadNotes(generationId,size=9) {
        if (this.generationId === generationId && this.boardSize === size) return;
        let saved = null;
        try { saved = JSON.parse(this.storage?.getItem(this.key) ?? 'null'); } catch { this.fail(); }
        this.generationId = generationId;
        this.boardSize = size;
        this.notes = {};
        if (generationId && saved?.generationId === generationId && saved.notes && typeof saved.notes === 'object') {
            for (const [index, values] of Object.entries(saved.notes)) {
                if (/^(0|[1-9]\d*)$/.test(index) && Number(index) < size**2 && Array.isArray(values)) {
                    this.notes[index] = [...new Set(values.filter(v => Number.isInteger(v) && v >= 1 && v <= size))];
                }
            }
        }
        this.saveNotes();
    }
    saveNotes() {
        try {
            if (!this.storage) throw new Error('Storage unavailable');
            this.storage.setItem(this.key, JSON.stringify({generationId:this.generationId,notes:this.notes,symbolSource:this.symbolSource}));
        } catch { this.fail(); }
        this.onChange();
    }
    openDatabase() {
        if (!this.databasePromise) this.databasePromise = new Promise((resolve, reject) => {
            const request = globalThis.indexedDB.open('sudoku-v2', 1);
            request.onupgradeneeded = () => request.result.createObjectStore('sprites');
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
            request.onblocked = () => reject(new Error('IndexedDB blocked'));
        });
        return this.databasePromise;
    }
    async loadSprite() {
        try {
            const db = await this.openDatabase();
            return await new Promise((resolve,reject) => {
                const request = db.transaction('sprites').objectStore('sprites').get(this.key);
                request.onsuccess = () => resolve(request.result ?? null);
                request.onerror = () => reject(request.error);
            });
        } catch { this.fail(); this.onChange(); return null; }
    }
    async saveSprite(blob) {
        this.sprite = blob;
        try {
            const db = await this.openDatabase();
            await new Promise((resolve,reject) => {
                const transaction = db.transaction('sprites','readwrite');
                transaction.objectStore('sprites').put(blob,this.key);
                transaction.oncomplete = resolve;
                transaction.onerror = () => reject(transaction.error);
                transaction.onabort = () => reject(transaction.error);
            });
        } catch { this.fail(); }
        this.onChange();
    }
}
