import test from 'node:test';
import assert from 'node:assert/strict';
import {SudokuConfig} from '../static/sudoku_vibe/js/config.js?v=11';
import {createGameState} from '../static/sudoku_vibe/js/state.js?v=11';
import {getNoteLayout} from '../static/sudoku_vibe/js/board.js?v=11';
test('older_revision_is_ignored across generations and empty snapshots clear values',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null}), store=createGameState(c);
    const b={name:'Иван',generationId:'B',revision:4,values:{'0':3},fixedCells:[]};
    store.applyBoard(b);store.applyBoard({...b,generationId:'A',revision:3,values:{'0':9}});
    assert.equal(store.getBoard('Иван').values['0'],3);
    store.applyBoard({...b,revision:5,values:{'0':''}});
    assert.equal(store.getBoard('Иван').values['0'],'');
});

test('participant snapshots remove departures and ignore their late moves',()=>{
    const c=new SudokuConfig({username:'me',storage:null}),store=createGameState(c);
    const me={name:'me',generationId:'A',revision:1,values:{},fixedCells:[]};
    const other={...me,name:'other'};
    store.applySnapshot({boards:[me,other]});
    store.applySnapshot({boards:[me]});
    store.applySnapshot({board:{...other,revision:2}});
    assert.deepEqual(store.getBoards().map(b=>b.name),['me']);
});

test('fresh room snapshot resets old revisions and local notes',()=>{
    const c=new SudokuConfig({username:'me',storage:null}),store=createGameState(c);
    store.applySnapshot({boards:[{name:'me',generationId:'old',revision:20,values:{'0':8},fixedCells:[]}]});
    c.local.notes={'1':[9]};
    store.applySnapshot({config:{username:'me',preferences:{}},boards:[{name:'me',generationId:null,revision:0,values:{},fixedCells:[]}]});
    assert.equal(store.getBoard('me').revision,0);
    assert.equal(store.getBoard('me').generationId,null);
    assert.deepEqual(c.local.notes,{});
});

test('notes use a square grid sized from board side',()=>{
    assert.deepEqual(getNoteLayout(9,9),{side:3,row:3,column:3});
    assert.deepEqual(getNoteLayout(16,16),{side:4,row:4,column:4});
    assert.deepEqual(getNoteLayout(10,10),{side:4,row:3,column:2});
});

test('snapshot subscribers see the complete roster and receive one store notification',()=>{
    const config=new SudokuConfig({username:'Zoe',storage:null}),store=createGameState(config);
    const own={name:'Zoe',generationId:'A',revision:1,values:{},fixedCells:[]};
    const seen=[];let notifications=0;
    config.subscribe(()=>seen.push(store.getBoards().map(b=>b.name)));
    store.subscribe(()=>{notifications++;seen.push(store.getBoards().map(b=>b.name));});
    store.applySnapshot({config:{username:'Zoe',preferences:{}},boards:[{...own,name:'Amy'},own]});
    assert.equal(notifications,1);
    for(const names of seen)assert.deepEqual(names,['Amy','Zoe']);
});
