import test from 'node:test';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';

test('bundled sheets include all sixteen square tiles',()=>{
    for(const name of ['digits','tokens']){
        const source=readFileSync(new URL(`../static/sudoku_v2/img/${name}.svg`,import.meta.url),'utf8');
        assert.match(source,/height="1024"/);
        assert.equal([...source.matchAll(/transform="translate\(0 \d+\)"/g)].length,16);
        assert.match(source,/>16<\/text>/);
    }
});
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
