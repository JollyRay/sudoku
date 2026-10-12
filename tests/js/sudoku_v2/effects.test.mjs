import test from 'node:test';
import assert from 'node:assert/strict';
import {createEffectsController} from '../../../sudoku_v2/static/sudoku_v2/js/effects.js?v=12';

function setup(){
    let now=0,next=0,changes=0;const tasks=new Map();
    const controller=createEffectsController({now:()=>now,
        setTimeoutFn:(fn,delay)=>{tasks.set(++next,{fn,at:now+delay});return next;},
        clearTimeoutFn:id=>tasks.delete(id),onChange:()=>changes++});
    return {controller,tasks,changes:()=>changes,tick(ms){now+=ms;
        for(const [id,task] of [...tasks])if(task.at<=now){tasks.delete(id);task.fn();}}};
}
const effect=(id,start=0)=>({id,kind:'SHADOW_BOX',params:{box:0,blurPx:6},startsAt:start,expiresAt:start+30000});
const board=(effects,generationId='A')=>({name:'me',generationId,activeEffects:effects});

test('same_effects_expire_independently',()=>{
    const c=setup();c.controller.reconcile(board([effect('A'),effect('B',10000)]));
    c.tick(30000);assert.deepEqual(c.controller.activeFor('me','A').map(e=>e.id),['B']);
    c.tick(10000);assert.deepEqual(c.controller.activeFor('me','A'),[]);assert.equal(c.changes(),2);
});
test('duplicate_event_does_not_restart_timer and late snapshot cannot resurrect',()=>{
    const c=setup();c.controller.reconcile(board([effect('A')]));c.tick(10000);
    c.controller.reconcile(board([effect('A')]));assert.equal(c.tasks.size,1);
    c.tick(20000);assert.deepEqual(c.controller.activeFor('me','A'),[]);
    c.controller.reconcile(board([effect('A')]));assert.equal(c.tasks.size,0);
    c.controller.dispose();
});
test('new_generation_clears_timers and dispose blocks late callbacks',()=>{
    const c=setup();c.controller.reconcile(board([effect('A')]));
    const stale=[...c.tasks.values()][0].fn;
    c.controller.reconcile(board([effect('B')],'B'));assert.equal(c.tasks.size,1);
    stale();assert.equal(c.changes(),0);assert.equal(c.controller.activeFor('me','B').length,1);
    c.controller.dispose();assert.equal(c.tasks.size,0);stale();assert.equal(c.changes(),0);
});
test('opponent_switch_restores_remaining_effects',()=>{
    const c=setup(),opponent={...board([effect('A')]),name:'other'};
    c.controller.reconcile(opponent);c.tick(15000);
    c.controller.reconcile({...board([]),name:'third'});c.tick(10000);
    c.controller.reconcile(opponent);assert.equal(c.controller.activeFor('other','A')[0].expiresAt,30000);
    c.tick(5000);assert.deepEqual(c.controller.activeFor('other','A'),[]);
});
