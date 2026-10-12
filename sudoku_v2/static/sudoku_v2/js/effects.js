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
const visualClasses = { SHADOW_BOX: 'effect-blur', ROLL: 'effect-roll', DANCE: 'effect-dance', GRAYSCALE: 'effect-gray', PULSE: 'effect-pulse' };
export function renderEffects(grid, board, effects, now) {
    for (const box of grid.querySelectorAll('.board-box')) {
        const instances = effects.filter((e) => e.params.box === Number(box.dataset.boxIndex) && visualClasses[e.kind]);
        const key = JSON.stringify([board.name, board.generationId, instances.map((e) => e.id)]);
        if (box.effectKey === key) continue;
        box.effectKey = key;
        const content = box.querySelector('.box-content');
        // Ordinary moves leave this entire chain intact. Only effect membership changes it.
        if (!instances.length && !box.querySelector('.effect-layer')) continue;
        const focused = document.activeElement, restore = content.contains(focused);
        box.replaceChildren(content);
        let parent = box;
        for (const effect of instances) {
            const layer = document.createElement('div');
            layer.className = `effect-layer ${visualClasses[effect.kind]}`;
            layer.dataset.effectId = effect.id;
            layer.setAttribute('role', 'presentation');
            const p = effect.params;
            layer.style.setProperty('--effect-blur', `${p.blurPx ?? 6}px`);
            layer.style.setProperty('--effect-angle', `${p.angleDegrees ?? 3}deg`);
            layer.style.setProperty('--effect-gray', String(p.amount ?? 1));
            layer.style.setProperty('--effect-opacity', String(p.minOpacity ?? 0.35));
            layer.style.animationDuration = `${p.periodMs ?? 4000}ms`;
            layer.style.animationDelay = `-${Math.max(0, now - effect.startsAt)}ms`;
            parent.append(layer);
            parent = layer;
        }
        parent.append(content);
        if (restore && document.activeElement !== focused) focused.focus({ preventScroll: true });
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
