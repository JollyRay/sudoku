export function createGameState(config) {
    const boards = new Map(), listeners = new Set(), localEdits = new Map();
    let activeNames = null, clockSynced = false;
    function syncClock(serverNow) {
        if (!Number.isFinite(serverNow)) return;
        const offset = serverNow - Date.now();
        // Accept real clock skew initially; queued messages cannot extend effects later.
        config.runtime.clockOffset = clockSynced ? Math.max(config.runtime.clockOffset, offset) : offset;
        clockSynced = true;
    }
    function updateBoard(board) {
        if (!board || typeof board.name !== 'string') return false;
        const previous = boards.get(board.name);
        if (previous && board.revision < previous.revision) return false;
        if (board.name === config.username &&
            (previous?.generationId !== board.generationId || board.completed)) localEdits.clear();
        boards.set(board.name, structuredClone(board));
        return true;
    }
    function publish() {
        const own = store.getBoard(config.username);
        if (own) {
            config.local.loadNotes(own.generationId,own.size??9);
            if(config.runtime.selectedCell>=(own.size??9)**2)config.runtime.selectedCell=null;
            let changed = false;
            for (const index of Object.keys(config.local.notes)) {
                if ((own.values?.[index] ?? '') !== '' || own.fixedCells?.includes(Number(index))) {
                    delete config.local.notes[index];
                    changed = true;
                }
            }
            if (changed) config.local.saveNotes();
        }
        for (const listener of listeners) listener();
    }
    const store = {
        catalog: {difficulties:[],sizes:[],bonuses:[],symbolPresets:[]},
        getBoard(name) {
            const board = boards.get(name);
            if (!board || name !== config.username || !localEdits.size) return board;
            const values = {...board.values};
            for (const [index, edit] of localEdits) values[index] = edit.value;
            return {...board, values, wrongCells: (board.wrongCells ?? []).filter(i => !localEdits.has(i))};
        },
        getBoards: () => [...boards.keys()].map(name => store.getBoard(name)),
        editCell(cellIndex, value) {
            const edit = {cellIndex, value};
            localEdits.set(cellIndex, edit);
            publish();
            return edit;
        },
        subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
        applyBoard(board) {
            if (!updateBoard(board)) return false;
            publish();
            return true;
        },
        applyBonusEvent(data) {
            syncClock(data.serverNow);
            for(const board of data.targets??[])if(!activeNames||activeNames.has(board.name))updateBoard(board);
            publish();
        },
        applySnapshot(data, acknowledgedEdit) {
            if (data.config?.username === config.username) localEdits.clear();
            if (acknowledgedEdit && localEdits.get(acknowledgedEdit.cellIndex) === acknowledgedEdit)
                localEdits.delete(acknowledgedEdit.cellIndex);
            if (data.catalog) store.catalog = data.catalog;
            syncClock(data.serverNow);
            if (Array.isArray(data.boards)) {
                if (data.config?.username === config.username) boards.clear();
                activeNames = new Set(data.boards.map(board=>board.name));
                for (const name of boards.keys()) if (!activeNames.has(name)) boards.delete(name);
                for (const board of data.boards) updateBoard(board);
            }
            if (data.board && (!activeNames || activeNames.has(data.board.name))) updateBoard(data.board);
            // Subscribers always see the full participant list, never a partial snapshot.
            if (data.config?.username === config.username) config.applyServerContext(data.config);
            publish();
        },
    };
    return store;
}
