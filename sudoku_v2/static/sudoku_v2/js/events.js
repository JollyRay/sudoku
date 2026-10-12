export function createEventBindings() {
    const bindings = [];
    return {
        bind(target, event, handler) {
            target.addEventListener(event, handler);
            bindings.push(() => target.removeEventListener(event, handler));
        },
        dispose() {
            bindings.forEach(remove => remove());
        },
    };
}
