import test from 'node:test';
import assert from 'node:assert/strict';
import {blockSide,canonicalIndex,displayPosition} from '../../../sudoku_v2/static/sudoku_v2/js/geometry.js?v=12';

test('geometry is reversible on both sizes with row and column permutations',()=>{
    for(const size of [9,16]){
        assert.equal(blockSide(size),Math.sqrt(size));
        const rows=Array.from({length:size},(_,i)=>i),cols=[...rows];
        [rows[0],rows[1]]=[rows[1],rows[0]];[cols[1],cols[2]]=[cols[2],cols[1]];
        for(let index=0;index<size**2;index++){
            const {row,col}=displayPosition(index,size,rows,cols);
            assert.equal(canonicalIndex(row,col,size,rows,cols),index);
        }
    }
    assert.deepEqual(displayPosition(255,16),{row:15,col:15});
    assert.equal(canonicalIndex(15,15,16),255);
    for(const size of [0,8,10,true])assert.throws(()=>blockSide(size));
});
