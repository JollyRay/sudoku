import test from 'node:test';
import assert from 'node:assert/strict';
import {SudokuConfig} from '../../../sudoku_v2/static/sudoku_v2/js/config.js?v=12';
import {createGameState} from '../../../sudoku_v2/static/sudoku_v2/js/state.js?v=12';
import {createInputController} from '../../../sudoku_v2/static/sudoku_v2/js/input.js?v=12';
import {formatElapsed} from '../../../sudoku_v2/static/sudoku_v2/js/ui.js?v=12';
function setup(){
    const config=new SudokuConfig({username:'me',allowedValues:['',1,2],storage:null});
    config.runtime.ready=true;
    const store=createGameState(config), sent=[];
    store.applyBoard({name:'me',generationId:'A',revision:1,size:9,values:{'0':'','1':9},fixedCells:[1],completed:false});
    const input=createInputController({store,config,sendCellValue:(...args)=>{sent.push(args);return true;}});
    input.selectCell(0);return {config,store,sent,input};
}

test('A through G enter 10 through 16 only on the active 16 board',()=>{
    const {config,store,sent,input}=setup();
    const key=k=>input.handleKeydown({key:k,target:{closest:()=>null},preventDefault(){}});
    config.setPreference('size',16);key('A');assert.equal(sent.length,0);
    store.applyBoard({...store.getBoard('me'),generationId:'B',revision:2,size:16});
    config.setAllowedValues(['',...Array.from({length:16},(_,i)=>i+1)]);
    key('a');key('G');assert.deepEqual(sent.map(args=>args[3]),[10,16]);
    config.setPreference('size',9);key('g');assert.equal(sent.at(-1)[3],16);
    input.selectCell(255);key('ArrowDown');assert.equal(config.runtime.selectedCell,255);
    key('0');assert.equal(sent.at(-1)[3],'');
    input.dispose();
});
test('ordinary input delegates the move; fixed cells cannot send',()=>{
    const {sent,input}=setup();input.enterValue(2);
    assert.deepEqual(sent,[['me','A',0,2]]);
    input.selectCell(1);input.enterValue(2);assert.equal(sent.length,1);
});
test('notes stay private and completion blocks all input',()=>{
    const {config,store,sent,input}=setup();config.setPreference('notesMode',true);
    input.enterValue(2);assert.deepEqual(config.local.notes['0'],[2]);assert.equal(sent.length,0);
    input.enterValue(2);assert.equal(config.local.notes['0'],undefined);
    input.enterValue(1);input.enterValue('');assert.deepEqual(config.local.notes,{});
    store.applyBoard({...store.getBoard('me'),revision:2,completed:true});
    input.enterValue(1);config.setPreference('notesMode',false);input.enterValue('');
    assert.equal(sent.length,0);assert.deepEqual(config.local.notes,{});
});
test('typing in settings does not play; full wrong boards remain editable',()=>{
    const {config,store,sent,input}=setup();
    const e={key:'2',target:{closest:()=>({})},preventDefault:()=>assert.fail('must not intercept')};
    input.handleKeydown(e);assert.equal(sent.length,0);
    store.applyBoard({...store.getBoard('me'),revision:2,values:{'0':1,'1':9},wrongCells:[0]});
    input.enterValue(2);assert.equal(sent.length,1);
    config.runtime.menuOpen=true;input.handleKeydown({...e,target:{closest:()=>null}});assert.equal(sent.length,1);
});
test('timers use server timestamps and completed timers stay frozen',()=>{
    assert.equal(formatElapsed({startedAt:null},99999),'00:00');
    assert.equal(formatElapsed({startedAt:1000,finishedAt:null},66000),'01:05');
    assert.equal(formatElapsed({startedAt:1000,finishedAt:46000},3600000),'00:45');
    assert.equal(formatElapsed({startedAt:1000,finishedAt:null},3662000),'1:01:01');
});

test('all board values count toward the digit limit; notes do not; erase unlocks',()=>{
    const {config,store,sent,input}=setup();
    const values=Object.fromEntries(Array.from({length:9},(_,i)=>[i,1]));
    store.applyBoard({...store.getBoard('me'),revision:2,values,fixedCells:[1],wrongCells:[0,2]});
    input.selectCell(10);config.local.notes={'10':[2], '11':[2]};
    assert.equal(input.canChooseValue(1),false);
    assert.equal(input.canChooseValue(2),true);
    input.enterValue(1);assert.equal(sent.length,0);
    input.selectCell(0);input.enterValue('');assert.equal(sent.at(-1)[3],'');
    store.applyBoard({...store.getBoard('me'),revision:3,values:{...values,'0':''}});
    assert.equal(input.canChooseValue(1),true);
    // A legacy overfilled board also blocks the digit.
    store.applyBoard({...store.getBoard('me'),revision:4,values:{...values,'10':1}});
    assert.equal(input.canChooseValue(1),false);
});

test('zero Delete and Backspace erase, including while a digit is forced',()=>{
    const {config,sent,input}=setup();config.setPreference('digitFirstMode',true);
    input.chooseValue(2);
    for(const [index,key] of ['0','Delete','Backspace'].entries()){
        let prevented=false;
        input.handleKeydown({key,target:{closest:()=>null},preventDefault(){prevented=true;}});
        assert.equal(prevented,true);assert.equal(sent.at(-1)[3],'');
        assert.equal(sent.length,index+1);
    }
    assert.equal(config.runtime.forcedValue,2);
});

test('digit first selects before writing, persists across clicks, focus does not write',()=>{
    const {config,store,sent,input}=setup();config.setPreference('digitFirstMode',true);
    input.selectCell(1); // Fixed or absent selection must not prevent choosing a digit.
    assert.equal(input.canChooseValue(2),true);input.chooseValue(2);
    assert.equal(sent.length,0);assert.equal(config.runtime.forcedValue,2);
    input.selectCell(0);assert.equal(sent.length,0);
    input.activateCell(0);assert.equal(sent.length,1);
    config.runtime.pending=true;config.emit();input.activateCell(2);assert.equal(sent.length,1);
    assert.equal(config.runtime.forcedValue,2);
    config.runtime.pending=false;
    store.applyBoard({...store.getBoard('me'),revision:2,values:{'0':2,'1':9}});
    input.activateCell(2);assert.equal(sent.length,2);assert.equal(sent.at(-1)[2],2);
    input.activateCell(1);assert.equal(sent.length,2);
    input.handleKeydown({key:'ArrowRight',target:{closest:()=>null},preventDefault(){}});
    assert.equal(sent.length,2);
    input.chooseValue(2);assert.equal(config.runtime.forcedValue,null);
    input.dispose();
});

test('forced choice resets on generation, limit, allowed values, completion and mode off',()=>{
    const {config,store,input}=setup();config.setPreference('digitFirstMode',true);
    input.chooseValue(2);
    store.applyBoard({...store.getBoard('me'),generationId:'B',revision:2});
    assert.equal(config.runtime.forcedValue,null);
    input.chooseValue(2);
    store.applyBoard({...store.getBoard('me'),revision:3,values:Object.fromEntries(Array.from({length:9},(_,i)=>[i,2]))});
    assert.equal(config.runtime.forcedValue,null);assert.equal(input.chooseValue(2),false);
    input.chooseValue(1);config.setPreference('digitFirstMode',false);
    assert.equal(config.runtime.forcedValue,null);
    config.setPreference('digitFirstMode',true);input.chooseValue(1);
    config.setAllowedValues(['',2]);config.emit();assert.equal(config.runtime.forcedValue,null);
    config.setAllowedValues(['',1,2]);input.chooseValue(1);
    store.applyBoard({...store.getBoard('me'),revision:4,completed:true});
    assert.equal(config.runtime.forcedValue,null);assert.equal(input.canChooseValue(1),false);
});

test('digit first notes remain local, can be erased with zero, respect limit',()=>{
    const {config,store,sent,input}=setup();
    config.setPreference('digitFirstMode',true);config.setPreference('notesMode',true);
    input.chooseValue(2);input.activateCell(0);assert.deepEqual(config.local.notes['0'],[2]);
    assert.equal(sent.length,0);
    input.handleKeydown({key:'0',target:{closest:()=>null},preventDefault(){}});
    assert.deepEqual(config.local.notes,{});assert.equal(sent.length,0);
    store.applyBoard({...store.getBoard('me'),revision:2,values:Object.fromEntries(Array.from({length:9},(_,i)=>[i+10,2]))});
    input.enterValue(2);assert.deepEqual(config.local.notes,{});
});

test('same-generation refresh preserves forced digit when opponents arrive first',()=>{
    const config=new SudokuConfig({username:'Zoe',storage:null}),store=createGameState(config);
    const own={name:'Zoe',generationId:'A',revision:1,size:9,values:{},fixedCells:[],completed:false};
    const data={config:{username:'Zoe',preferences:{digitFirstMode:true}},boards:[{...own,name:'Amy'},own]};
    store.applySnapshot(data);config.runtime.ready=true;
    const input=createInputController({store,config,sendCellValue:()=>true});input.chooseValue(2);
    store.applySnapshot(data);assert.equal(config.runtime.forcedValue,2);
    store.applySnapshot({...data,boards:[data.boards[0],{...own,generationId:'B',revision:2}]});
    assert.equal(config.runtime.forcedValue,null);input.dispose();
});
