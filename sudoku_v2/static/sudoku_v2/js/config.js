import {LocalContext} from './local-context.js?v=12';

const DEFAULT_ALLOWED_VALUES = Object.freeze(['',1,2,3,4,5,6,7,8,9]);
const DEFAULT_PREFERENCES = Object.freeze({difficulty:'medium',size:9,notesMode:false,showErrors:false,digitFirstMode:false,
    symbolPresetId:'plain',selectedOpponent:null,twitchChannel:'',twitchCooldown:0});

export class SudokuConfig {
    constructor({room='',username='undefined',allowedValues=DEFAULT_ALLOWED_VALUES,storage}={}) {
        this.listeners = new Set();
        this.room = room;
        this.username = username;
        this.setAllowedValues(allowedValues);
        this.preferences = {...DEFAULT_PREFERENCES};
        this.preferenceVersion = 0;
        this.dirtyPreferences = new Map();
        this.runtime = {ready:false,status:'connecting',selectedCell:null,forcedValue:null,menuOpen:false,
            pending:false,clockOffset:0,message:'',symbolSheet:null,
            twitch:{bindings:[],workerStatus:'disabled',serverNow:0}};
        this.local = new LocalContext(room,username,{storage,onChange:()=>this.emit('local')});
    }
    setAllowedValues(values) {
        if (!Array.isArray(values) || values.some(v=>v!=='' && (!Number.isInteger(v)||v<0||v>16))) throw new TypeError('Invalid values');
        this.allowedValues = [...new Set(values.filter(value=>value!==0))];
    }
    subscribe(listener) { this.listeners.add(listener); return ()=>this.listeners.delete(listener); }
    emit(reason='runtime') { for(const listener of this.listeners) listener(reason); }
    setPreference(key,value) {
        if (!(key in DEFAULT_PREFERENCES)) throw new TypeError('Unknown preference');
        if (this.preferences[key] === value) return;
        this.preferences[key] = value;
        this.dirtyPreferences.set(key,{value,version:++this.preferenceVersion});
        this.emit('preferences');
    }
    applyServerContext(context) {
        if (context.username !== this.username) return false;
        if (context.allowedValues) this.setAllowedValues(context.allowedValues);
        this.preferences = {...DEFAULT_PREFERENCES,...context.preferences};
        for (const [key,entry] of this.dirtyPreferences) this.preferences[key]=entry.value;
        this.emit();
        return true;
    }
    ackContext(context,version) {
        if (context.username !== this.username) return;
        for(const [key,entry] of this.dirtyPreferences) if(entry.version<=version) this.dirtyPreferences.delete(key);
        this.applyServerContext(context);
    }
    toSendableContext() {
        return {
            username: this.username,
            allowedValues: [...this.allowedValues],
            preferences: {...this.preferences},
        };
    }
}
