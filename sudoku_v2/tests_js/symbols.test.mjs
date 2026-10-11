import test from 'node:test';
import assert from 'node:assert/strict';
import {getSpriteRect} from '../static/sudoku_v2/js/symbols.js?v=12';
import {LocalContext} from '../static/sudoku_v2/js/local-context.js?v=12';
test('short_sprite_is_white and partial or extra tiles are accepted',()=>{
    assert.deepEqual(getSpriteRect(32,64,3),{sx:0,sy:64,sw:32,sh:0,size:32});
    assert.deepEqual(getSpriteRect(32,80,3),{sx:0,sy:64,sw:32,sh:16,size:32});
    assert.deepEqual(getSpriteRect(32,384,12),{sx:0,sy:352,sw:32,sh:32,size:32});
});
test('persistence_failure_keeps_memory_state',async()=>{
    const local=new LocalContext('room','name',{storage:null});
    const blob=new Blob(['image']);await local.saveSprite(blob);
    assert.equal(local.sprite,blob);assert.ok(local.persistenceError);
    local.notes={'0':[3]};local.saveNotes();assert.deepEqual(local.notes,{'0':[3]});
    local.symbolSource='custom';local.loadNotes('generation-2');
    assert.equal(local.symbolSource,'custom');assert.equal(local.sprite,blob);
});
