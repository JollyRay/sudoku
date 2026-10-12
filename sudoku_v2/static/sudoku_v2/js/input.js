import { canonicalIndex, displayPosition } from './geometry.js?v=12';
export function createInputController({ store, config, sendCellValue }) {
    const ownBoard = () => store.getBoard(config.username);
    let generationId = ownBoard()?.generationId;
    function boardEditable() {
        const b = ownBoard();
        return Boolean(b?.generationId && !b.completed && !b.requiresGeneration && config.runtime.status !== 'closed' && !config.runtime.pending);
    }
    function hasCapacity(value) {
        const b = ownBoard();
        return value === '' || Object.values(b?.values ?? {}).filter((v) => v === value).length < (b?.size ?? 9);
    }
    function canEnter() {
        const b = ownBoard(), index = config.runtime.selectedCell;
        return Boolean(boardEditable() && Number.isInteger(index) && index >= 0 && index < (b.size ?? 9) ** 2 && !b.fixedCells.includes(index) && (!config.preferences.notesMode || (b.values[index] ?? '') === ''));
    }
    function canChooseValue(value) {
        return boardEditable() && Number.isInteger(value) && value >= 1 && value <= (ownBoard()?.size ?? 9) && config.allowedValues.includes(value) && hasCapacity(value) && (config.preferences.digitFirstMode || canEnter());
    }
    function reconcileChoice() {
        const b = ownBoard(), value = config.runtime.forcedValue;
        if (!b) return;
        if (generationId !== b?.generationId || !config.preferences.digitFirstMode || b?.completed || b?.requiresGeneration || value !== null && (!config.allowedValues.includes(value) || !hasCapacity(value))) {
            config.runtime.forcedValue = null;
        }
        generationId = b?.generationId;
    }
    function selectCell(index) {
        if (!Number.isInteger(index) || index < 0 || index >= (ownBoard()?.size ?? 9) ** 2) return false;
        config.runtime.selectedCell = index;
        config.emit();
        return true;
    }
    function activateCell(index) {
        if (!selectCell(index)) return false;
        if (config.preferences.digitFirstMode && config.runtime.forcedValue !== null) {
            return enterValue(config.runtime.forcedValue);
        }
        return false;
    }
    function chooseValue(value) {
        if (!canChooseValue(value)) return false;
        if (!config.preferences.digitFirstMode) return enterValue(value);
        config.runtime.forcedValue = config.runtime.forcedValue === value ? null : value;
        config.emit();
        return true;
    }
    function enterValue(value) {
        if (!canEnter() || !hasCapacity(value) || value !== '' && (!Number.isInteger(value) || value < 1 || value > (ownBoard()?.size ?? 9) || !config.allowedValues.includes(value))) return false;
        const b = ownBoard(), index = config.runtime.selectedCell;
        if (config.preferences.notesMode) {
            if ((b.values[index] ?? '') !== '') return false;
            const values = new Set(config.local.notes[index] ?? []);
            if (value === '') values.clear();
            else if (values.has(value)) values.delete(value);
            else values.add(value);
            if (values.size) config.local.notes[index] = [...values].sort((a, b) => a - b);
            else delete config.local.notes[index];
            config.local.saveNotes();
            return true;
        }
        return sendCellValue(config.username, b.generationId, index, value);
    }
    function handleKeydown(event) {
        if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey || event.isComposing || config.runtime.menuOpen || event.target?.closest?.('input,select,textarea,[contenteditable="true"],dialog[open]')) return;
        const board = ownBoard(), size = board?.size ?? 9;
        const deltas = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
        if (event.key in deltas) {
            event.preventDefault();
            const current = Math.min(size ** 2 - 1, config.runtime.selectedCell ?? 0);
            const { row, col } = displayPosition(current, size, board?.rowOrder, board?.columnOrder), [dr, dc] = deltas[event.key];
            selectCell(canonicalIndex(Math.max(0, Math.min(size - 1, row + dr)), Math.max(0, Math.min(size - 1, col + dc)), size, board?.rowOrder, board?.columnOrder));
        } else if (event.key === '0' || event.key === 'Backspace' || event.key === 'Delete') {
            event.preventDefault();
            enterValue('');
        } else if (/^[1-9]$/.test(event.key) || size === 16 && /^[a-g]$/i.test(event.key)) {
            event.preventDefault();
            const value = /^[a-g]$/i.test(event.key) ? event.key.toUpperCase().charCodeAt(0) - 55 : Number(event.key);
            if (!event.repeat || !config.preferences.digitFirstMode) chooseValue(value);
        }
    }
    const subscriptions = [store.subscribe(reconcileChoice), config.subscribe(reconcileChoice)];
    reconcileChoice();
    return {
        selectCell,
        activateCell,
        chooseValue,
        enterValue,
        handleKeydown,
        canEnter,
        canChooseValue,
        hasCapacity,
        dispose() {
            subscriptions.forEach((unsubscribe) => unsubscribe());
        }
    };
}
