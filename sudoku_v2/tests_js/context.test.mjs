import test from 'node:test';
import assert from 'node:assert/strict';
import {SudokuConfig} from '../static/sudoku_v2/js/config.js?v=12';
import {createGameState} from '../static/sudoku_v2/js/state.js?v=12';
import {connectWebsocket} from '../static/sudoku_v2/js/network.js?v=12';
import {createInputController} from '../static/sudoku_v2/js/input.js?v=12';

const board = (overrides={}) => ({name:'Иван',generationId:'A',revision:1,size:9,
    values:{'0':'','1':2},fixedCells:[1],bonuses:{},wrongCells:[],startedAt:1000,
    finishedAt:null,completed:false,requiresGeneration:false,...overrides});

test('16 board notes restore canonical indices and values; shrinking discards them',()=>{
    const memory=new Map(),storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};
    const original=new SudokuConfig({username:'Иван',storage});
    original.local.loadNotes('sixteen',16);original.local.notes={255:[10,16],256:[1]};original.local.saveNotes();
    const restored=new SudokuConfig({username:'Иван',storage}),store=createGameState(restored);
    store.applyBoard(board({size:16,generationId:'sixteen',values:{},fixedCells:[]}));
    assert.deepEqual(restored.local.notes,{255:[10,16]});
    restored.runtime.selectedCell=255;store.applyBoard(board({generationId:'nine',revision:2}));
    assert.deepEqual(restored.local.notes,{});assert.equal(restored.runtime.selectedCell,null);
});
class Socket extends EventTarget {
    static instances=[];
    readyState=0; sent=[];
    constructor(){super();Socket.instances.push(this);}
    send(raw){this.sent.push(JSON.parse(raw));}
    fire(type,data){
        if(type==='open')this.readyState=1;
        if(type==='close')this.readyState=3;
        const e=new Event(type);e.data=JSON.stringify(data);e.code=data?.code;this.dispatchEvent(e);
    }
    close(){this.fire('close',{code:1006});}
}

test('context sent during generation is fenced by its original board; stale context preserves move acknowledgements',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(c);
    const net=connectWebsocket({store,config:c,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',preferences:{}}}});
    net.requestBoardGeneration('medium',16);c.setPreference('showErrors',true);
    assert.equal(ws.sent.at(-1).data.generationId,'A');
    ws.fire('message',{kind:'board_data',data:{board:board({generationId:'B',revision:2}),config:{username:'Иван',preferences:{}}}});
    net.sendCellValue('Иван','B',0,3);
    ws.fire('message',{kind:'error',data:{code:'stale_context'}});
    assert.equal(store.getBoard('Иван').values[0],3);
    assert.equal(ws.sent.at(-1).kind,'get_board_data');
    ws.fire('message',{kind:'set_value',data:{board:board({generationId:'B',revision:3,values:{0:3}})}});
    ws.fire('message',{kind:'board_data',data:{board:board({generationId:'B',revision:3,values:{0:3}}),config:{username:'Иван',preferences:{}}}});
    assert.equal(ws.sent.at(-1).kind,'set_context');
    assert.equal(ws.sent.at(-1).data.generationId,'B');
    assert.equal(ws.sent.at(-1).data.preferences.showErrors,true);
    net.dispose();
});
test('context excludes local fields and preserves changes newer than an acknowledgement',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null});
    c.local.notes={'0':[2]};c.local.sprite=new Blob(['private']);
    c.setPreference('showErrors',true);const version=c.preferenceVersion;
    c.setPreference('twitchChannel','123');
    c.setPreference('digitFirstMode',true);c.runtime.forcedValue=3;
    c.ackContext({username:'Иван',allowedValues:[1,2],preferences:{showErrors:true,twitchChannel:''}},version);
    assert.equal(c.preferences.twitchChannel,'123');
    assert.deepEqual(Object.keys(c.toSendableContext()).sort(),['allowedValues','preferences','username']);
    assert.equal(c.toSendableContext().preferences.digitFirstMode,true);
    assert.equal(c.applyServerContext({username:'other',allowedValues:[9]}),false);
    assert.deepEqual(c.allowedValues,[1,2]);
});
test('reconnect_preserves_context_and_notes',()=>{
    const memory=new Map();const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};
    const c=new SudokuConfig({room:'r',username:'Иван',storage});const store=createGameState(c);
    store.applyBoard(board());c.local.notes={'0':[3]};c.local.saveNotes();
    const restored=new SudokuConfig({room:'r',username:'Иван',storage});const again=createGameState(restored);
    again.applyBoard(board());assert.deepEqual(restored.local.notes,{'0':[3]});
    again.applyBoard(board({revision:2}));assert.deepEqual(restored.local.notes,{'0':[3]});
    again.applyBoard(board({generationId:'B',revision:3}));assert.deepEqual(restored.local.notes,{});
    const net=connectWebsocket({store,config:c,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    assert.deepEqual(ws.sent,[{kind:'get_board_data',data:{}}]);
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',allowedValues:[1],preferences:{showErrors:true}},catalog:{}}});
    assert.equal(c.preferences.showErrors,true);assert.equal(c.runtime.ready,true);
    net.dispose();
});

test('settings edited during save are sent after the previous acknowledgement',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null});const store=createGameState(c);
    const net=connectWebsocket({store,config:c,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',allowedValues:[1],preferences:{}},catalog:{}}});
    c.setPreference('showErrors',true);
    ws.fire('message',{kind:'error',data:{code:'stale_generation'}});
    c.setPreference('twitchChannel','new_channel');
    assert.equal(ws.sent.filter(m=>m.kind==='set_context').length,1);
    ws.fire('message',{kind:'context_data',data:{config:{username:'Иван',allowedValues:[1],preferences:{showErrors:true,twitchChannel:''}}}});
    assert.equal(c.preferences.twitchChannel,'new_channel');
    // A stale generation pauses sending until the replacement snapshot arrives.
    assert.equal(ws.sent.filter(m=>m.kind==='set_context').length,1);
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',allowedValues:[1],preferences:{showErrors:true,twitchChannel:''}}}});
    const saves=ws.sent.filter(m=>m.kind==='set_context');
    assert.equal(saves.length,2);assert.equal(saves[1].data.preferences.twitchChannel,'new_channel');
    net.dispose();
});

test('local context is scoped to both room and user',()=>{
    const memory=new Map(),storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};
    const first=new SudokuConfig({room:'one',username:'Иван',storage});
    first.local.loadNotes('A');first.local.notes={'0':[2]};first.local.saveNotes();
    for(const [room,username] of [['two','Иван'],['one','Лена']]){
        const other=new SudokuConfig({room,username,storage});other.local.loadNotes('A');
        assert.deepEqual(other.local.notes,{});
    }
});

test('zero is removed from defaults and legacy context and notes',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null});
    assert.deepEqual(c.allowedValues,['',1,2,3,4,5,6,7,8,9]);
    c.applyServerContext({username:'Иван',allowedValues:['',0,2,9],preferences:{}});
    assert.deepEqual(c.allowedValues,['',2,9]);
    const storage={getItem:()=>JSON.stringify({generationId:'A',notes:{'0':[0,1,9]}}),setItem:()=>{}};
    const restored=new SudokuConfig({username:'Иван',storage});
    restored.local.loadNotes('A');
    assert.deepEqual(restored.local.notes,{'0':[1,9]});
});

test('participant events update roster without acknowledging generation',()=>{
    const c=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(c);
    const net=connectWebsocket({store,config:c,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),boards:[board(),board({name:'Лена'})],config:{username:'Иван',preferences:{}}}});
    net.requestBoardGeneration('easy');
    ws.fire('message',{kind:'participants_data',data:{boards:[board()]}});
    assert.equal(c.runtime.pending,true);
    assert.deepEqual(store.getBoards().map(b=>b.name),['Иван']);
    net.dispose();
});

test('bonus events do not acknowledge sent moves or generation requests',()=>{
    const config=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(config);
    const net=connectWebsocket({store,config,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',preferences:{}}}});
    net.sendCellValue('Иван','A',0,1);net.sendCellValue('Иван','A',0,2);
    ws.fire('message',{kind:'bonus_applied',data:{targets:[board({revision:2,values:{0:''},rowOrder:[1,0,2,3,4,5,6,7,8]})]}});
    ws.fire('message',{kind:'set_value',data:{board:board({revision:3,values:{0:1}})}});
    assert.equal(store.getBoard('Иван').values[0],2);
    ws.fire('message',{kind:'set_value',data:{board:board({revision:4,values:{0:2}})}});
    net.requestBoardGeneration('easy');
    ws.fire('message',{kind:'bonus_applied',data:{targets:[board({revision:5})]}});
    assert.equal(config.runtime.pending,true);net.dispose();
});

test('moves display immediately; older replies cannot overwrite later input to the same cell',()=>{
    const config=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(config);
    const net=connectWebsocket({store,config,WebSocketClass:Socket,url:'ws://test',reconnect:false});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',preferences:{}}}});
    const input=createInputController({store,config,sendCellValue:net.sendCellValue});input.selectCell(0);
    for(const value of [1,2,1]){
        assert.equal(input.enterValue(value),true);assert.equal(store.getBoard('Иван').values[0],value);
    }
    assert.equal(ws.sent.filter(m=>m.kind==='set_value').length,3);
    ws.fire('message',{kind:'participants_data',data:{boards:[board()]}});
    assert.equal(store.getBoard('Иван').values[0],1);
    ws.fire('message',{kind:'set_value',data:{board:board({revision:2,values:{0:1,1:2}})}});
    assert.equal(store.getBoard('Иван').values[0],1);
    ws.fire('message',{kind:'set_value',data:{board:board({revision:3,values:{0:2,1:2}})}});
    assert.equal(store.getBoard('Иван').values[0],1);
    ws.fire('message',{kind:'error',data:{code:'invalid_value',message:'Недопустимое значение.'}});
    assert.equal(store.getBoard('Иван').values[0],2);assert.equal(config.runtime.message,'Недопустимое значение.');
    assert.equal(input.enterValue(''),true);assert.equal(store.getBoard('Иван').values[0],'');
    ws.fire('message',{kind:'set_value',data:{board:board({revision:4,values:{0:'',1:2}})}});
    assert.equal(store.getBoard('Иван').values[0],'');
    input.dispose();net.dispose();
});

test('offline input stays local and is discarded, never replayed, after reconnect',t=>{
    t.mock.timers.enable({apis:['setTimeout']});
    const config=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(config);
    const net=connectWebsocket({store,config,WebSocketClass:Socket,url:'ws://test'});
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',preferences:{}}}});
    const input=createInputController({store,config,sendCellValue:net.sendCellValue});input.selectCell(0);
    input.enterValue(1);ws.close();
    assert.equal(config.runtime.ready,false);
    assert.equal(input.enterValue(2),true);assert.equal(store.getBoard('Иван').values[0],2);
    assert.equal(ws.sent.filter(m=>m.kind==='set_value').length,1);
    input.selectCell(1);assert.equal(input.enterValue(3),false);
    t.mock.timers.tick(1000);const next=Socket.instances.at(-1);assert.notEqual(next,ws);
    next.fire('open');
    next.fire('message',{kind:'board_data',data:{board:board(),config:{username:'Иван',preferences:{}}}});
    assert.equal(store.getBoard('Иван').values[0],'');
    assert.deepEqual(next.sent,[{kind:'get_board_data',data:{}}]);
    input.selectCell(0);assert.equal(input.enterValue(3),true);
    assert.equal(next.sent.at(-1).data.value,3);
    input.dispose();net.dispose();
});

test('duplicate names return to the join screen without an error notice or retry',t=>{
    t.mock.timers.enable({apis:['setTimeout']});
    const config=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(config);
    let redirects=0;
    const net=connectWebsocket({store,config,WebSocketClass:Socket,url:'ws://test',returnToJoin:()=>redirects++});
    const ws=Socket.instances.at(-1),count=Socket.instances.length;ws.fire('open');
    ws.fire('close',{code:4409});t.mock.timers.tick(20000);
    assert.equal(redirects,1);assert.equal(config.runtime.message,'');
    assert.equal(Socket.instances.length,count);net.dispose();
});
