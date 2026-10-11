import test from 'node:test';
import assert from 'node:assert/strict';
import {renderNumberPad} from '../static/sudoku_v2/js/ui.js?v=12';
import {renderBoard} from '../static/sudoku_v2/js/board.js?v=12';
import {SudokuConfig} from '../static/sudoku_v2/js/config.js?v=12';
import {createGameState} from '../static/sudoku_v2/js/state.js?v=12';
import {createInputController} from '../static/sudoku_v2/js/input.js?v=12';

// The renderer only needs element creation, children, attributes and classes.
class Element {
    constructor(tag) {
        this.tagName=tag;this.children=[];this.dataset={};this.style={};this.attributes={};
        this.className='';this.disabled=false;
        this.classList={
            contains:name=>this.className.split(' ').includes(name),
            toggle:(name,on)=>{
                const classes=new Set(this.className.split(' ').filter(Boolean));
                if(on)classes.add(name);else classes.delete(name);
                this.className=[...classes].join(' ');
            },
        };
    }
    set textContent(value){this.replaceChildren({textContent:String(value)});}
    get textContent(){return this.children.map(c=>c.textContent).join('');}
    get firstElementChild(){return this.children[0]??null;}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    setAttribute(name,value){this.attributes[name]=value;}
    removeAttribute(name){delete this.attributes[name];}
    querySelectorAll(selector){
        const matches=node=>selector.startsWith('.')?node.classList.contains(selector.slice(1)):
            selector==='[data-cell-index]'?node.dataset.cellIndex!==undefined:node.tagName===selector;
        return this.children.flatMap(child=>child instanceof Element?
            [...(matches(child)?[child]:[]),...child.querySelectorAll(selector)]:[]);
    }
    querySelector(selector){return this.querySelectorAll(selector)[0]??null;}
}
function withDocument(t) {
    const previous=Object.getOwnPropertyDescriptor(globalThis,'document');
    Object.defineProperty(globalThis,'document',{configurable:true,value:{createElement:tag=>{
        const element=new Element(tag);
        if(tag==='canvas')element.getContext=()=>({fillRect(){},drawImage(){}});
        return element;
    }}});
    t.after(()=>{if(previous)Object.defineProperty(globalThis,'document',previous);else delete globalThis.document;});
}
function setup(t) {
    withDocument(t);
    const config=new SudokuConfig({username:'me',storage:null}),store=createGameState(config);
    config.runtime.ready=true;config.preferences.digitFirstMode=true;
    const board={name:'me',size:9,generationId:'A',revision:1,values:Object.fromEntries(Array.from({length:8},(_,i)=>[i,1])),fixedCells:[0],bonuses:{},wrongCells:[]};
    store.applyBoard(board);
    const input=createInputController({store,config,sendCellValue:()=>true});t.after(()=>input.dispose());
    return {config,store,board,input};
}

test('board switches 9 to 16 to 9 and own to opponent; stable renders keep cell nodes',t=>{
    const {config,board}=setup(t),host=new Element('div');
    for(const [size,name] of [[9,'me'],[16,'me'],[16,'other'],[9,'other']]){
        config.local.notes[0]=[1,16];
        const current={...board,size,name,values:{1:size},fixedCells:[]};
        const grid=renderBoard(host,current,{config});
        const cells=grid.querySelectorAll('[data-cell-index]');
        assert.equal(cells.length,size**2);
        assert.equal(grid.querySelectorAll('.board-box').length,size);
        assert.equal(cells[0].tagName,name==='me'?'button':'span');
        assert.equal(renderBoard(host,current,{config}),grid);
        assert.equal(grid.querySelectorAll('[data-cell-index]')[0],cells[0]);
        const number=cells.find(cell=>Number(cell.dataset.cellIndex)===1);
        assert.equal(number.querySelector('.digit').textContent,String(size));
        if(size===16&&name==='me')assert.equal(cells[0].querySelector('.cell-notes').style.gridTemplateColumns,'repeat(4,minmax(0,1fr))');
    }
});

test('number keys and glyphs survive selection, pending, exhaustion and erase',t=>{
    const {config,store,board,input}=setup(t),pad=new Element('div');
    const update=()=>renderNumberPad(pad,{config,input});
    update();const keys=[...pad.children],glyphs=keys.map(key=>key.firstElementChild.firstElementChild);
    config.runtime.forcedValue=1;config.runtime.selectedCell=8;update();
    config.runtime.pending=true;update();assert.equal(keys[0].disabled,true);
    assert.equal(keys[0].classList.contains('is-exhausted'),false);
    config.runtime.pending=false;
    store.applyBoard({...board,revision:2,values:{...board.values,8:1}});update();
    assert.equal(keys[0].classList.contains('is-exhausted'),true);assert.equal(keys[0].disabled,true);
    assert.equal(keys[1].classList.contains('is-exhausted'),false);assert.equal(keys[1].disabled,false);
    store.applyBoard({...board,revision:3});update();
    assert.equal(keys[0].classList.contains('is-exhausted'),false);assert.equal(keys[0].disabled,false);
    keys.forEach((key,i)=>{assert.equal(pad.children[i],key);assert.equal(key.firstElementChild.firstElementChild,glyphs[i]);});
});

test('number pad refreshes glyphs for a new theme and rebuilds only a changed value set',t=>{
    const {config,input}=setup(t),pad=new Element('div');
    renderNumberPad(pad,{config,input});const first=pad.children[0];
    config.runtime.symbolSheet={width:16,height:144,image:{},tiles:new Map()};
    renderNumberPad(pad,{config,input});assert.equal(pad.children[0],first);
    const canvas=first.firstElementChild.firstElementChild;
    assert.equal(canvas.tagName,'canvas');
    renderNumberPad(pad,{config,input});assert.equal(first.firstElementChild.firstElementChild,canvas);
    config.runtime.symbolSheet={width:16,height:144,image:{},tiles:new Map()};
    renderNumberPad(pad,{config,input});assert.notEqual(first.firstElementChild.firstElementChild,canvas);
    config.runtime.symbolSheet=null;renderNumberPad(pad,{config,input});
    assert.equal(pad.children[0],first);assert.equal(first.firstElementChild.textContent,'1');
    config.setAllowedValues(['',2,3]);renderNumberPad(pad,{config,input});
    assert.deepEqual(pad.children.map(key=>Number(key.dataset.value)),[2,3]);
});

test('board retains unchanged text, note and bonus nodes; edits update only affected contents',t=>{
    const {config,board}=setup(t),host=new Element('div');
    config.local.notes[8]=[2,9];board.bonuses={8:'ROLL'};
    config.runtime.bonusCatalog=[{id:'ROLL',symbol:'↻',label:'Поворот'}];
    const table=renderBoard(host,board,{config}),cells=table.querySelectorAll('[data-cell-index]').sort((a,b)=>Number(a.dataset.cellIndex)-Number(b.dataset.cellIndex));
    const digit=cells[0].querySelector('.digit'),notes=cells[8].querySelector('.cell-notes'),bonus=cells[8].querySelector('.bonus-mark');
    const text=digit.firstElementChild,note=notes.firstElementChild,mark=bonus.firstElementChild;
    renderBoard(host,board,{config,selectedCell:20});config.runtime.pending=true;
    renderBoard(host,board,{config,selectedCell:21});
    assert.equal(digit.firstElementChild,text);assert.equal(notes.firstElementChild,note);assert.equal(bonus.firstElementChild,mark);
    config.local.notes[8]=[3];renderBoard(host,board,{config});assert.equal(notes.textContent,'3');
    board.values[8]=4;renderBoard(host,board,{config});assert.equal(notes.children.length,0);
    assert.equal(cells[8].querySelector('.digit').textContent,'4');assert.equal(digit.firstElementChild,text);
});

test('swap moves a canonical cell with its notes and consumed marker without replacing it',t=>{
    const {config,board}=setup(t),host=new Element('div');
    config.local.notes[8]=[2,9];board.bonuses={8:'ROLL'};
    const grid=renderBoard(host,board,{config,selectedCell:8});
    const cell=grid.querySelectorAll('[data-cell-index]').find(c=>Number(c.dataset.cellIndex)===8);
    board.rowOrder=[1,0,2,3,4,5,6,7,8];board.columnOrder=[0,1,2,3,4,5,6,8,7];board.consumedBonusCells=[8];
    renderBoard(host,board,{config,selectedCell:8});
    assert.equal(grid.querySelectorAll('[data-cell-index]').find(c=>Number(c.dataset.cellIndex)===8),cell);
    assert.equal(cell.style.gridArea,'2 / 2');assert.equal(cell.querySelector('.cell-notes').textContent,'29');
    assert.equal(cell.classList.contains('is-bonus-consumed'),true);
    assert.match(cell.attributes['aria-label'],/использован/);
    assert.equal(cell.querySelector('.bonus-mark').textContent,'◇');
});
