import test from 'node:test';
import assert from 'node:assert/strict';
import {SudokuConfig} from '../../../sudoku_v2/static/sudoku_v2/js/config.js?v=12';
import {createGameState} from '../../../sudoku_v2/static/sudoku_v2/js/state.js?v=12';
import {connectWebsocket} from '../../../sudoku_v2/static/sudoku_v2/js/network.js?v=12';
import {mountTwitchSettings} from '../../../sudoku_v2/static/sudoku_v2/js/twitch.js?v=15';

class Socket extends EventTarget {
    static instances=[]; readyState=0; sent=[];
    constructor(){super();Socket.instances.push(this);}
    send(raw){this.sent.push(JSON.parse(raw));}
    fire(type,data){if(type==='open')this.readyState=1;if(type==='close')this.readyState=3;
        const e=new Event(type);e.data=JSON.stringify(data);e.code=data?.code;this.dispatchEvent(e);}
    close(){this.fire('close',{code:1006});}
}
const board=(revision,values)=>({name:'Иван',generationId:'A',revision,size:9,values,fixedCells:[],bonuses:{}});
function setup(t,options={}) {
    const config=new SudokuConfig({username:'Иван',storage:null}),store=createGameState(config);
    const net=connectWebsocket({store,config,WebSocketClass:Socket,url:'ws://test',reconnect:false,...options});
    t.after(()=>net.dispose());
    const ws=Socket.instances.at(-1);ws.fire('open');
    ws.fire('message',{kind:'board_data',data:{board:board(1,{7:''}),config:{username:'Иван',preferences:{}}}});
    return {config,store,net,ws};
}

test('Twitch errors and replies cannot acknowledge or erase optimistic moves',async t=>{
    const {config,store,net,ws}=setup(t);
    net.sendCellValue('Иван','A',7,4);
    const pending=net.connectTwitch('channel',15),requestId=ws.sent.at(-1).data.requestId;
    ws.fire('message',{kind:'error',data:{requestId,requestKind:'connect_twitch',code:'channel_in_use',message:'Занято'}});
    await assert.rejects(pending,/Занято/);
    assert.equal(store.getBoard(config.username).values[7],4);
    net.sendCellValue('Иван','A',7,5);
    ws.fire('message',{kind:'set_value',data:{board:board(2,{7:4})}});
    assert.equal(store.getBoard(config.username).values[7],5);
    ws.fire('message',{kind:'set_value',data:{board:board(3,{7:5})}});
    store.applyBoard(board(4,{7:6}));
    assert.equal(store.getBoard(config.username).values[7],6);
});

test('late Twitch request response cannot replace a newer status',async t=>{
    const {config,net,ws}=setup(t);
    const first=net.getTwitchStatus(),a=ws.sent.at(-1).data.requestId;
    const second=net.disconnectTwitch('channel'),b=ws.sent.at(-1).data.requestId;
    ws.fire('message',{kind:'twitch_status',data:{requestId:b,bindings:[],workerStatus:'disabled',serverNow:20}});
    await second;
    ws.fire('message',{kind:'twitch_status',data:{requestId:a,bindings:[{channel:'old'}],serverNow:10}});
    await first;
    assert.deepEqual(config.runtime.twitch.bindings,[]);
    ws.fire('message',{kind:'twitch_status',data:{requestId:'unrecognized',bindings:[{channel:'bogus'}],serverNow:30}});
    assert.deepEqual(config.runtime.twitch.bindings,[]);
});

test('Twitch timeout and offline reject separately from game requests',async t=>{
    const {config,store,net,ws}=setup(t,{twitchTimeoutMs:5});
    net.sendCellValue('Иван','A',7,4);
    await assert.rejects(net.connectTwitch('channel',0),/Twitch/);
    assert.equal(store.getBoard(config.username).values[7],4);
    const pending=net.getTwitchStatus();ws.close();
    await assert.rejects(pending,/связ/i);
    assert.equal(ws.sent.filter(m=>m.kind==='connect_twitch').length,1);
});

test('successful automatic poll clears refresh error but preserves a rejected user action',async t=>{
    const ids=['channel','cooldown','connect','disconnect','refresh','bindings','status','message'];
    const elements=Object.fromEntries(ids.map(id=>{
        const el=new EventTarget();Object.assign(el,{value:'',textContent:'',dataset:{},replaceChildren(){}});
        Object.defineProperty(el,'valueAsNumber',{get:()=>Number(el.value)});return [`twitch-${id}`,el];
    }));
    const previous=globalThis.document;globalThis.document={activeElement:null,createElement:()=>({dataset:{}})};
    t.after(()=>{globalThis.document=previous;});
    let tick;t.mock.method(globalThis,'setInterval',fn=>{tick=fn;return 0;});t.mock.method(globalThis,'clearInterval',()=>{});
    const config=new SudokuConfig({username:'Иван',storage:null});config.runtime.ready=true;config.preferences.twitchChannel='channel';
    let reads=0;
    const network={getTwitchStatus:async()=>{if(!reads++)throw new Error('Ответ Twitch задерживается');return {};},
        connectTwitch:async()=>{throw new Error('Канал занят');}};
    const dispose=mountTwitchSettings({querySelector:s=>elements[s.slice(1)]},{config,network});t.after(dispose);
    const flush=()=>new Promise(resolve=>setImmediate(resolve));
    await flush();assert.match(elements['twitch-message'].textContent,/задерживается/);
    tick();await flush();assert.equal(elements['twitch-message'].hidden,true);
    elements['twitch-connect'].dispatchEvent(new Event('click'));await flush();
    assert.equal(elements['twitch-message'].textContent,'Канал занят');
    tick();await flush();assert.equal(elements['twitch-message'].textContent,'Канал занят');
});
