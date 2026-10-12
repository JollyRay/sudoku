const MEDIA = '(min-width: 900px) and (pointer: fine)';
const ROW = 24, MARGIN = 12;
export function mountLayout(root, {
    matchMedia = window.matchMedia.bind(window),
    GridStackClass = window.GridStack,
    ResizeObserverClass = globalThis.ResizeObserver
} = {}) {
    const host = root.querySelector('#play-layout'), reset = root.querySelector('#reset-layout');
    const panels = ['own-panel', 'controls-panel', 'opponent-panel'].map((id) => root.querySelector(`#${id}`));
    const media = matchMedia(MEDIA);
    let grid = null, disposed = false, custom = false, updating = false;
    let hasOpponents = !panels[2].hidden;
    const visible = () => panels.filter((_, i) => i !== 2 || hasOpponents);
    const minWidth = () => Math.min(12, Math.ceil((320 + 32 + 2 * MARGIN) / (host.getBoundingClientRect().width / 12)));
    function defaults() {
        const width = host.getBoundingClientRect().width / 2 - 2 * MARGIN - 32;
        const ownH = Math.ceil((width + 152) / ROW), x = hasOpponents ? 0 : 3;
        return [{ x, y: 0, w: 6, h: ownH }, { x, y: ownH, w: 6, h: 15 }, { x: 6, y: 0, w: 6, h: ownH + 8 }];
    }
    function fit() {
        if (!grid || updating || disposed) return;
        updating = true;
        grid.batchUpdate();
        for (const panel of visible()) {
            const node = panel.gridstackNode;
            if (!node) continue;
            const minH = Math.ceil((panel.querySelector('.panel-body').scrollHeight + 32 + 2 * MARGIN) / ROW);
            const minW = minWidth();
            if (node.minH !== minH || node.minW !== minW || node.h < minH)
                grid.update(panel, { minH, minW, h: Math.max(node.h, minH) });
        }
        if (!custom && panels[0].gridstackNode && panels[1].gridstackNode)
            grid.update(panels[1], { y: panels[0].gridstackNode.h });
        grid.batchUpdate(false);
        updating = false;
    }
    function applyDefaults() {
        if (!grid) return;
        custom = false;
        const positions = defaults();
        grid.batchUpdate();
        for (const panel of visible()) grid.update(panel, { ...positions[panels.indexOf(panel)], minW: minWidth(), minH: 1 });
        grid.batchUpdate(false);
        fit();
    }
    function clearGeometry() {
        const focused = globalThis.document?.activeElement;
        host.removeAttribute('style');
        host.classList.remove('grid-stack', 'layout-desktop');
        for (const panel of panels) {
            panel.classList.remove('grid-stack-item');
            panel.removeAttribute('style');
            for (const attribute of [...panel.attributes]) if (attribute.name.startsWith('gs-')) panel.removeAttribute(attribute.name);
        }
        host.append(...panels);
        if (focused?.isConnected && globalThis.document.activeElement !== focused) focused.focus({ preventScroll: true });
    }
    function deactivate() {
        if (grid) {
            grid.destroy(false);
            grid = null;
        }
        clearGeometry();
        reset.hidden = true;
    }
    function activate() {
        if (disposed) return;
        if (!media.matches || !GridStackClass) {
            deactivate();
            return;
        }
        if (grid) return;
        host.classList.add('grid-stack', 'layout-desktop');
        custom = false;
        grid = GridStackClass.init({
            column: 12,
            cellHeight: ROW,
            margin: MARGIN,
            auto: false,
            animate: false,
            mode: 'float',
            handle: '.panel-drag-handle',
            draggable: { cancel: 'input,textarea,select,option,.cell' },
            resizable: { handles: 'se' },
            alwaysShowResizeHandle: true
        }, host);
        const positions = defaults();
        grid.batchUpdate();
        for (const panel of visible()) {
            panel.classList.add('grid-stack-item');
            grid.makeWidget(panel, { ...positions[panels.indexOf(panel)], id: panel.id, minW: minWidth() });
        }
        grid.batchUpdate(false);
        grid.on('dragstart resizestart', () => {
            custom = true;
        });
        grid.on('dragstop resizestop', fit);
        reset.hidden = false;
        fit();
    }
    const observer = ResizeObserverClass ? new ResizeObserverClass(fit) : null;
    for (const panel of panels) observer?.observe(panel.querySelector('.panel-body'));
    media.addEventListener('change', activate);
    reset.addEventListener('click', applyDefaults);
    activate();
    return {
        refreshParticipants(value) {
            if (value !== hasOpponents) {
                hasOpponents = value;
                if (grid) {
                    const panel = panels[2];
                    if (value) {
                        panel.classList.add('grid-stack-item');
                        grid.makeWidget(panel, { ...defaults()[2], id: panel.id, minW: minWidth() });
                    } else {
                        grid.removeWidget(panel, false, false);
                        panel.classList.remove('grid-stack-item');
                        panel.removeAttribute('style');
                    }
                    if (!custom) applyDefaults();
                }
            }
            fit();
        },
        dispose() {
            disposed = true;
            observer?.disconnect();
            media.removeEventListener('change', activate);
            reset.removeEventListener('click', applyDefaults);
            deactivate();
        }
    };
}
