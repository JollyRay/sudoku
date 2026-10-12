import test from 'node:test';
import assert from 'node:assert/strict';
import {mountLayout} from '../../../sudoku_v2/static/sudoku_v2/js/layout.js?v=12';

function setup(matches){
    const writes=[],calls=[],listeners=new Map();
    const element=id=>({id,hidden:false,attributes:[],style:{},classList:{add(){},remove(){}},
        getBoundingClientRect:()=>({width:1080,height:200}),querySelector:()=>({scrollHeight:200}),
        removeAttribute(){},addEventListener:(k,v)=>listeners.set(id+k,v),removeEventListener:k=>listeners.delete(id+k),append(...nodes){calls.push(['order',...nodes.map(n=>n.id)]);}});
    const elements=Object.fromEntries(['play-layout','own-panel','controls-panel','opponent-panel','reset-layout'].map(id=>[id,element(id)]));
    const media={matches,addEventListener:(_,fn)=>media.change=fn,removeEventListener:()=>media.change=null};
    class Observer{constructor(fn){this.fn=fn;calls.push(['observer',this]);}observe(){}disconnect(){calls.push(['disconnect']);}}
    const GridStackClass={init(options,el){calls.push(['init',options,el]);const grid={
        on:(events,fn)=>{calls.push(['on',events]);for(const event of events.split(' '))listeners.set(event,fn);return grid;},
        batchUpdate(){return grid;},makeWidget(panel,options){panel.gridstackNode={...options};calls.push(['make',panel.id]);},
        update(panel,options){Object.assign(panel.gridstackNode,options);},
        removeWidget(panel,removeDOM){calls.push(['remove',panel.id,removeDOM]);delete panel.gridstackNode;},
        destroy(removeDOM){calls.push(['destroy',removeDOM]);for(const p of Object.values(elements))delete p.gridstackNode;},
    };return grid;}};
    const original=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
    Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{setItem:(...args)=>writes.push(args)}});
    const mount=()=>mountLayout({querySelector:s=>elements[s.slice(1)]},{matchMedia:()=>media,GridStackClass,ResizeObserverClass:Observer});
    return {mount,calls,listeners,media,elements,writes,restore(){if(original)Object.defineProperty(globalThis,'localStorage',original);else delete globalThis.localStorage;}};
}
test('mobile/coarse pointer has no grid; desktop mounts three panels and only handle drags',()=>{
    const s=setup(false);try{const layout=s.mount();assert.equal(s.calls.filter(c=>c[0]==='init').length,0);
        s.media.matches=true;s.media.change();assert.equal(s.calls.filter(c=>c[0]==='make').length,3);
        assert.equal(s.calls.find(c=>c[0]==='init')[1].handle,'.panel-drag-handle');
        s.media.matches=false;s.media.change();assert.deepEqual(s.calls.filter(c=>c[0]==='order').at(-1),['order','own-panel','controls-panel','opponent-panel']);
        layout.dispose();assert.deepEqual(s.calls.find(c=>c[0]==='destroy'),['destroy',false]);
        assert.equal(s.media.change,null);assert.ok(s.calls.some(c=>c[0]==='disconnect'));
    }finally{s.restore();}
});
test('departure removes only opponent item; layout is memory-only and remount uses defaults',()=>{
    const s=setup(true);try{const layout=s.mount();const initial={...s.elements['own-panel'].gridstackNode};
        s.listeners.get('dragstart')();s.elements['own-panel'].gridstackNode.x=5;s.listeners.get('dragstop')?.();
        s.listeners.get('resizestart')();s.listeners.get('resizestop')?.();
        layout.refreshParticipants(false);assert.deepEqual(s.calls.filter(c=>c[0]==='remove'),[['remove','opponent-panel',false]]);
        assert.equal(s.calls.filter(c=>c[0]==='make'&&c[1]==='own-panel').length,1);
        layout.dispose();const next=s.mount();assert.equal(s.elements['own-panel'].gridstackNode.x,initial.x);
        next.dispose();assert.deepEqual(s.writes,[]);
    }finally{s.restore();}
});
