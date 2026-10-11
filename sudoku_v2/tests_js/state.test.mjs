import test from 'node:test';
import assert from 'node:assert/strict';
import {SudokuConfig} from '../static/sudoku_v2/js/config.js?v=12';
import {createGameState} from '../static/sudoku_v2/js/state.js?v=12';
import {getNoteLayout} from '../static/sudoku_v2/js/board.js?v=12';
import {createEffectsController} from '../static/sudoku_v2/js/effects.js?v=12';

test('late ordinary snapshots cannot extend a newer bonus effect',t=>{
    t.mock.timers.enable({apis:['Date','setTimeout'],now:100000});
    for(const key of ['board','boards']){
        const config=new SudokuConfig({username:'me',storage:null}),store=createGameState(config);
        const effects=createEffectsController({now:()=>Date.now()+config.runtime.clockOffset});
        const start=Date.now(),board={name:'me',size:9,generationId:'A',revision:1,values:{},fixedCells:[]};
        store.subscribe(()=>effects.reconcile(store.getBoard('me')));
        store.applySnapshot({board,serverNow:start});
        const effect={id:'A',kind:'ROLL',params:{box:0},startsAt:start,expiresAt:start+30000};
        store.applyBonusEvent({serverNow:start,targets:[{...board,revision:2,activeEffects:[effect]}]});
        t.mock.timers.tick(10000);
        store.applySnapshot({[key]:key==='boards'?[board]:board,serverNow:start});
        assert.equal(store.getBoard('me').revision,2);
        t.mock.timers.tick(20001);
        assert.deepEqual(effects.activeFor('me','A'),[]);
        effects.dispose();
    }
});

test('first clock sync accepts a server behind the client on either message path',t=>{
    t.mock.timers.enable({apis:['Date'],now:100000});
    for(const method of ['applySnapshot','applyBonusEvent']){
        const config=new SudokuConfig({username:'me',storage:null}),store=createGameState(config);
        store[method]({serverNow:90000});
        assert.equal(config.runtime.clockOffset,-10000);
        store.applySnapshot({serverNow:80000});
        assert.equal(config.runtime.clockOffset,-10000);
        store.applyBonusEvent({serverNow:95000});
        assert.equal(config.runtime.clockOffset,-5000);
    }
});

test('late and duplicate bonus events cannot rewind server time or extend effects',t=>{
    t.mock.timers.enable({apis:['Date','setTimeout'],now:100000});
    const config=new SudokuConfig({username:'me',storage:null}),store=createGameState(config);
    const effects=createEffectsController({now:()=>Date.now()+config.runtime.clockOffset});
    const board={name:'me',size:9,generationId:'A',revision:1,values:{},fixedCells:[]};
    store.subscribe(()=>effects.reconcile(store.getBoard('me')));
    store.applySnapshot({board,serverNow:100000});
    const effect={id:'A',kind:'ROLL',params:{box:0},startsAt:100000,expiresAt:130000};
    const data={eventId:'A',serverNow:100000,targets:[{...board,revision:2,activeEffects:[effect]}]};
    store.applyBonusEvent(data);t.mock.timers.tick(10000);store.applyBonusEvent(data);
    t.mock.timers.tick(20000);assert.deepEqual(effects.activeFor('me','A'),[]);
    // Even an unseen delayed event uses the established clock, not its old timestamp.
    store.applyBonusEvent({...data,eventId:'B',targets:[{...board,revision:3,activeEffects:[{...effect,id:'B'}]}]});
    assert.deepEqual(effects.activeFor('me','A'),[]);effects.dispose();
});
test('bonus_delta_preserves_other_participants_and_local_edits',()=>{
    const config=new SudokuConfig({username:'me',storage:null}),store=createGameState(config);
    const own={name:'me',size:9,generationId:'A',revision:1,values:{},fixedCells:[]};
    store.applySnapshot({boards:[own,{...own,name:'other'},{...own,name:'third'}]});
    const first=store.editCell(0,1);store.editCell(0,2);config.local.notes[1]=[4];
    store.applyBonusEvent({targets:[{...own,revision:2,values:{0:1},rowOrder:[1,0,2,3,4,5,6,7,8]}]});
    assert.equal(store.getBoards().length,3);assert.equal(store.getBoard('me').values[0],2);
    assert.deepEqual(config.local.notes[1],[4]);
    store.applySnapshot({board:{...own,revision:3,values:{0:1}}},first);
    assert.equal(store.getBoard('me').values[0],2);
    store.applySnapshot({boards:[own]});
    store.applyBonusEvent({targets:[{...own,name:'other',revision:4}]});
    assert.equal(store.getBoards().length,1);
});
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
