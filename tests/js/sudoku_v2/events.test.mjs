import test from 'node:test';
import assert from 'node:assert/strict';
import {createEventBindings} from '../../../sudoku_v2/static/sudoku_v2/js/events.js?v=12';

test('disposing one group leaves other handlers on the same target active', () => {
    const target = new EventTarget();
    const first = createEventBindings();
    const second = createEventBindings();
    const calls = [];
    first.bind(target, 'click', function () {
        assert.equal(this, target);
        calls.push('first');
    });
    second.bind(target, 'click', () => calls.push('second'));

    target.dispatchEvent(new Event('click'));
    first.dispose();
    first.dispose();
    target.dispatchEvent(new Event('click'));
    second.dispose();
    target.dispatchEvent(new Event('click'));

    assert.deepEqual(calls, ['first', 'second', 'second']);
});

test('cleanup covers multiple targets and event types before a fresh mount', () => {
    const board = new EventTarget();
    const menu = new EventTarget();
    let calls = 0;
    const handler = () => calls++;
    const bindings = createEventBindings();
    bindings.bind(board, 'click', handler);
    bindings.bind(board, 'focusin', handler);
    bindings.bind(menu, 'close', handler);
    bindings.dispose();

    const remounted = createEventBindings();
    remounted.bind(board, 'click', handler);
    board.dispatchEvent(new Event('click'));
    board.dispatchEvent(new Event('focusin'));
    menu.dispatchEvent(new Event('close'));
    assert.equal(calls, 1);
    remounted.dispose();
});
