export function createEffectsController({ now = Date.now, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout, onChange = () => {
} } = {}) {
    const records = new Map();
    let disposed = false;
    const clear = (record) => {
        for (const entry of record.active.values()) clearTimeoutFn(entry.timer);
    };
    function schedule(name, record, entry) {
        entry.timer = setTimeoutFn(() => {
            if (disposed || records.get(name) !== record || record.active.get(entry.effect.id) !== entry) return;
            if (entry.effect.expiresAt > now()) {
                schedule(name, record, entry);
                return;
            }
            record.active.delete(entry.effect.id);
            onChange();
        }, Math.max(0, entry.effect.expiresAt - now()));
    }
    return {
        reconcile(board) {
            if (disposed) return;
            let record = records.get(board.name);
            if (!record || record.generation !== board.generationId) {
                if (record) clear(record);
                record = { generation: board.generationId, active: new Map(), seen: new Set() };
                records.set(board.name, record);
            }
            const effects = board.activeEffects ?? [], incoming = new Set(effects.map((e) => e.id));
            for (const [id, entry] of record.active) if (!incoming.has(id) || entry.effect.expiresAt <= now()) {
                clearTimeoutFn(entry.timer);
                record.active.delete(id);
            }
            for (const effect of effects) {
                if (record.seen.has(effect.id)) continue;
                record.seen.add(effect.id);
                if (effect.expiresAt <= now()) continue;
                const entry = { effect: structuredClone(effect), timer: null };
                record.active.set(effect.id, entry);
                schedule(board.name, record, entry);
            }
        },
        activeFor(name, generationId) {
            const record = records.get(name);
            return record?.generation === generationId ? [...record.active.values()].map((e) => e.effect).filter((e) => e.expiresAt > now()) : [];
        },
        dispose() {
            disposed = true;
            for (const record of records.values()) clear(record);
            records.clear();
        }
    };
}
const visualClasses = { SHADOW_BOX: 'effect-blur', ROLL: 'effect-roll', DANCE: 'effect-dance' };
function renderLayers(target, content, instances, board, now) {
    const key = JSON.stringify([board.name, board.generationId, instances.map((e) => e.id)]);
    if (target.effectKey === key) return false;
    target.effectKey = key;
    // Ordinary moves leave the layers and their animation phases intact.
    if (!instances.length && !target.querySelector('.effect-layer')) return false;
    const focused = document.activeElement;
    const restore = content.some((node) => node.contains(focused));
    target.replaceChildren(...content);
    let parent = target;
    for (const effect of instances) {
        const dancing = effect.kind === 'DANCE';
        const layer = document.createElement(dancing ? 'span' : 'div');
        layer.className = `effect-layer ${visualClasses[effect.kind]}`;
        layer.dataset.effectId = effect.id;
        layer.setAttribute('role', 'presentation');
        if (dancing) {
            const index = Number(target.dataset.cellIndex), base = Math.sqrt(board.size);
            const localIndex = Math.floor(index / board.size) % base * base + index % base;
            layer.style.setProperty('--dance-direction', localIndex % 2 ? '1' : '-1');
        }
        const p = effect.params;
        layer.style.setProperty('--effect-blur', `${p.blurPx ?? 6}px`);
        layer.style.animationDuration = `${p.periodMs ?? (dancing ? 5000 : 4000)}ms`;
        layer.style.animationDelay = `-${Math.max(0, now - effect.startsAt)}ms`;
        parent.append(layer);
        parent = layer;
    }
    parent.append(...content);
    if (restore && document.activeElement !== focused) focused.focus({ preventScroll: true });
    return true;
}
export function renderEffects(grid, board, effects, now) {
    for (const box of grid.querySelectorAll('.board-box')) {
        const instances = effects.filter((e) => e.params.box === Number(box.dataset.boxIndex) && visualClasses[e.kind]);
        const dances = instances.filter((e) => e.kind === 'DANCE');
        const boxChanged = renderLayers(box, [box.querySelector('.box-content')],
            instances.filter((e) => e.kind !== 'DANCE'), board, now);
        for (const cell of box.querySelectorAll('[data-cell-index]')) {
            // Moving box-content restarts CSS animations; restore each dance's current phase.
            if (boxChanged) cell.effectKey = null;
            const parts = ['.digit', '.cell-notes', '.bonus-mark'].map((selector) => cell.querySelector(selector));
            renderLayers(cell, parts, dances, board, now);
        }
    }
}
export function effectBadges(board, effects, catalog, now) {
    const groups = new Map();
    for (const effect of effects) {
        const group = groups.get(effect.kind) ?? { count: 0, expiresAt: 0 };
        group.count++;
        group.expiresAt = Math.max(group.expiresAt, effect.expiresAt);
        groups.set(effect.kind, group);
    }
    const result = [];
    for (const [kind, group] of groups) {
        const definition = catalog.find((b) => b.id === kind);
        result.push({
            text: `${definition?.symbol ?? '◇'} ×${group.count} ${Math.ceil((group.expiresAt - now) / 1000)}с`,
            label: `${definition?.label ?? kind}: ${group.count}, осталось ${Math.ceil((group.expiresAt - now) / 1000)} с`
        });
    }
    if ([board.rowOrder, board.columnOrder].some((order) => order?.some((v, i) => v !== i)))
        result.push({ text: '⇄', label: 'Строки или столбцы переставлены до новой доски' });
    return result;
}
