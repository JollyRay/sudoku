import {renderBoard} from './board.js?v=12';
import {createInputController} from './input.js?v=12';
import {loadSymbolSheet,renderSymbol,disposeSymbolSheet} from './symbols.js?v=12';

export function formatElapsed(board,nowMs) {
    if(board?.startedAt==null)return '00:00';
    const seconds=Math.max(0,Math.floor(((board.finishedAt??nowMs)-board.startedAt)/1000));
    const minutes=Math.floor(seconds/60),s=String(seconds%60).padStart(2,'0');
    return minutes>=60?`${Math.floor(minutes/60)}:${String(minutes%60).padStart(2,'0')}:${s}`:`${String(minutes).padStart(2,'0')}:${s}`;
}
const emptyBoard=name=>({name,size:9,values:{},fixedCells:[],wrongCells:[],bonuses:{},generationId:null,revision:0});
const progress=board=>`${Object.values(board?.values??{}).filter(v=>v!=='').length} / ${(board?.size??9)**2}`;
export function renderNumberPad(container,{config,input}) {
    const values=config.allowedValues.filter(value=>value!==''),signature=JSON.stringify(values);
    container.dataset.size=values.length>9?'16':'9';
    if(container.dataset.values!==signature){
        container.replaceChildren(...values.map(value=>{
            const button=document.createElement('button');button.type='button';button.className='number-key';button.dataset.value=value;
            const span=document.createElement('span');span.className='key-symbol';button.append(span);
            return button;
        }));
        container.dataset.values=signature;
    }
    for(const key of container.children){
        const value=Number(key.dataset.value),disabled=!input.canChooseValue(value);
        if(key.disabled!==disabled)key.disabled=disabled;
        key.classList.toggle('is-exhausted',!input.hasCapacity(value));
        if(config.preferences.digitFirstMode)key.setAttribute('aria-pressed',String(config.runtime.forcedValue===value));
        else key.removeAttribute('aria-pressed');
        key.setAttribute('aria-label',`${config.preferences.digitFirstMode?'Выбрать':'Ввести'} ${value}`);
        renderSymbol(key.firstElementChild,value,config.runtime.symbolSheet);
    }
}
export function mountGame(root,{store,config,network}) {
    const $=id=>root.querySelector(`#${id}`);
    const input=createInputController({store,config,sendCellValue:network.sendCellValue});
    const bindings=[];
    const bind=(el,name,fn)=>{el.addEventListener(name,fn);bindings.push(()=>el.removeEventListener(name,fn));};
    $('room-name').textContent=config.room;$('own-name').textContent=config.username;
    bind($('own-board'),'click',e=>{const cell=e.target.closest('[data-cell-index]');if(cell)input.activateCell(Number(cell.dataset.cellIndex));});
    bind($('own-board'),'focusin',e=>{const cell=e.target.closest('[data-cell-index]');if(cell&&Number(cell.dataset.cellIndex)!==config.runtime.selectedCell)input.selectCell(Number(cell.dataset.cellIndex));});
    bind(document,'keydown',e=>{input.handleKeydown(e);if(e.defaultPrevented&&e.key.startsWith('Arrow'))$('own-board').querySelector(`[data-cell-index="${config.runtime.selectedCell}"]`)?.focus();});
    bind($('number-pad'),'click',e=>{const key=e.target.closest('[data-value]');if(key)input.chooseValue(Number(key.dataset.value));});
    bind($('erase-value'),'click',()=>input.enterValue(''));
    bind($('notes-mode'),'click',()=>config.setPreference('notesMode',!config.preferences.notesMode));
    bind($('show-errors'),'click',()=>config.setPreference('showErrors',!config.preferences.showErrors));
    bind($('digit-first'),'click',()=>config.setPreference('digitFirstMode',!config.preferences.digitFirstMode));
    bind($('difficulty'),'change',e=>config.setPreference('difficulty',e.target.value));
    bind($('board-size'),'change',e=>config.setPreference('size',Number(e.target.value)));
    bind($('generate-board'),'click',()=>network.requestBoardGeneration(config.preferences.difficulty,config.preferences.size));
    bind($('opponent-list'),'click',e=>{
        const button=e.target.closest('[data-opponent]');
        if(button)config.setPreference('selectedOpponent',button.dataset.opponent);
    });
    const fillSelect=(el,options,value)=>{
        const signature=JSON.stringify(options);
        if(el.dataset.options!==signature){el.replaceChildren(...options.map(([v,label])=>new Option(label,v)));el.dataset.options=signature;}
        el.value=value??'';
    };
    let opponent=null;
    const participantButtons=new Map();
    const updateTimers=()=>{
        const now=Date.now()+config.runtime.clockOffset;
        $('own-timer').textContent=formatElapsed(store.getBoard(config.username),now);
        $('opponent-timer').textContent=formatElapsed(opponent,now);
        for(const [name,button] of participantButtons)button.querySelector('time').textContent=formatElapsed(store.getBoard(name),now);
    };
    function render() {
        const own=store.getBoard(config.username)??emptyBoard(config.username);
        const others=store.getBoards().filter(b=>b.name!==config.username);
        opponent=others.find(b=>b.name===config.preferences.selectedOpponent)??others[0]??null;
        config.runtime.bonusCatalog=store.catalog.bonuses??[];
        const highlightValue=config.preferences.digitFirstMode?config.runtime.forcedValue:null;
        renderBoard($('own-board'),own,{config,selectedCell:config.runtime.selectedCell,highlightValue});
        if(opponent)renderBoard($('opponent-board'),opponent,{config});
        $('opponent-panel').hidden=!opponent;
        $('play-layout').classList.toggle('is-solo',!opponent);
        $('opponent-name').textContent=opponent?.name??'Игроки комнаты';
        const activeNames=new Set(others.map(board=>board.name));
        for(const [name,button] of participantButtons)if(!activeNames.has(name)){button.remove();participantButtons.delete(name);}
        for(const board of others){
            let button=participantButtons.get(board.name);
            if(!button){
                button=document.createElement('button');button.type='button';button.className='opponent-choice';button.dataset.opponent=board.name;
                const name=document.createElement('span');name.className='opponent-choice-name';name.textContent=board.name;
                const count=document.createElement('span');count.className='opponent-choice-progress';
                const time=document.createElement('time');
                button.append(name,count,time);participantButtons.set(board.name,button);$('opponent-list').append(button);
            }
            button.setAttribute('aria-pressed',String(board.name===opponent?.name));
            button.querySelector('.opponent-choice-progress').textContent=progress(board);
        }
        $('own-progress').textContent=progress(own);$('opponent-progress').textContent=progress(opponent);
        renderNumberPad($('number-pad'),{config,input});
        const erase=$('erase-value'),canErase=input.canEnter();
        erase.classList.toggle('is-unavailable',!canErase);
        erase.disabled=!canErase;
        for(const [id,prop] of [['notes-mode','notesMode'],['show-errors','showErrors'],['digit-first','digitFirstMode']]){
            $(id).setAttribute('aria-pressed',String(config.preferences[prop]));
            $(id).disabled=!own.generationId||config.runtime.status==='closed'||(id!=='show-errors'&&Boolean(own.completed));
        }
        fillSelect($('difficulty'),(store.catalog.difficulties??[]).map(d=>[d.value,d.label]),config.preferences.difficulty);
        fillSelect($('board-size'),(store.catalog.sizes??[]).map(n=>[String(n),`${n} × ${n}`]),String(config.preferences.size));
        $('generate-board').disabled=!config.runtime.ready||config.runtime.pending||!store.catalog.difficulties?.length;
        $('connection-status').dataset.status=config.runtime.status;
        $('connection-status').textContent={connecting:'Подключение…',connected:config.runtime.ready?'В комнате':'Загружаем поле…',offline:'Нет связи',closed:'Соединение закрыто'}[config.runtime.status];
        const message=config.runtime.message||config.runtime.imageMessage||config.local.persistenceError||(config.runtime.ready&&!store.catalog.difficulties?.length?'Пока нет доступных сложностей. Добавьте задачи на сервере.':'');
        $('game-message').textContent=message;$('game-message').hidden=!message;
        updateTimers();
    }
    const unsubscribeStore=store.subscribe(render),unsubscribeConfig=config.subscribe(render);
    const disposeSettings=mountSettings(root,{config,store});
    const timer=setInterval(updateTimers,1000);bind(document,'visibilitychange',updateTimers);
    render();
    return {dispose(){unsubscribeStore();unsubscribeConfig();input.dispose();disposeSettings();clearInterval(timer);bindings.forEach(fn=>fn());}};
}

function mountSettings(root,{config,store}) {
    const $=id=>root.querySelector(`#${id}`),dialog=$('settings-dialog'),bindings=[];
    let disposed=false,selectionVersion=0,loadVersion=0,sheet=null,lastSource,loadingSource;
    const bind=(el,event,fn)=>{el.addEventListener(event,fn);bindings.push(()=>el.removeEventListener(event,fn));};
    bind($('open-menu'),'click',()=>{dialog.showModal();config.runtime.menuOpen=true;config.emit();});
    bind($('close-menu'),'click',()=>dialog.close());
    bind(dialog,'close',()=>{config.runtime.menuOpen=false;config.emit();$('open-menu').focus();});
    bind(dialog,'click',e=>{if(e.target===dialog && e.clientX>dialog.getBoundingClientRect().right)dialog.close();});
    bind($('twitch-channel'),'input',e=>config.setPreference('twitchChannel',e.target.value));
    const preview=()=>{
        const size=store.getBoard(config.username)?.size??9;
        $('symbol-preview').dataset.size=String(size);
        $('symbol-preview').replaceChildren(...Array.from({length:size},(_,i)=>{
            const element=document.createElement('span');element.setAttribute('aria-label',String(i+1));renderSymbol(element,i+1,sheet);return element;
        }));
    };
    const showSheet=next=>{
        disposeSymbolSheet(sheet);sheet=next;config.runtime.symbolSheet=sheet;preview();
        config.emit();
    };
    const refreshSymbols=async()=>{
        const preset=store.catalog.symbolPresets?.find(p=>p.id===config.preferences.symbolPresetId);
        const source=config.local.symbolSource==='custom'&&config.local.sprite?config.local.sprite:preset?.imageUrl??null;
        if(source===lastSource) {
            if(loadingSource!==undefined&&loadingSource!==source){loadVersion++;loadingSource=undefined;}
            return;
        }
        if(source===loadingSource)return;
        loadingSource=source;const version=++loadVersion;
        try {
            const next=source?await loadSymbolSheet(source):null;
            if(disposed||version!==loadVersion){disposeSymbolSheet(next);return;}
            lastSource=source;loadingSource=undefined;config.runtime.imageMessage='';showSheet(next);
        } catch {
            if(disposed||version!==loadVersion)return;
            loadingSource=undefined;lastSource=source;
            config.runtime.imageMessage='Не удалось открыть изображение. Выберите другой файл или набор.';config.emit();
        }
    };
    bind($('symbol-preset'),'change',e=>{
        selectionVersion++;
        config.local.symbolSource=e.target.value==='custom'?'custom':'preset';
        if(e.target.value!=='custom')config.setPreference('symbolPresetId',e.target.value);
        config.local.saveNotes();
    });
    bind($('symbol-file'),'change',async e=>{
        const file=e.target.files[0];if(!file)return;
        const version=++selectionVersion;
        try {
            const decoded=await loadSymbolSheet(file);disposeSymbolSheet(decoded);
            if(disposed||version!==selectionVersion)return;
            config.local.sprite=file;config.local.symbolSource='custom';config.runtime.imageMessage='';
            config.local.saveNotes();await config.local.saveSprite(file);
        } catch {
            if(!disposed&&version===selectionVersion){config.runtime.imageMessage='Не удалось открыть файл как изображение. Предыдущее оформление сохранено.';config.emit();}
        } finally {e.target.value='';}
    });
    function update() {
        if($('symbol-preview').dataset.size!==String(store.getBoard(config.username)?.size??9))preview();
        const message=config.runtime.message||config.runtime.imageMessage||config.local.persistenceError;
        $('settings-message').textContent=message;$('settings-message').hidden=!message;
        const presets=store.catalog.symbolPresets??[];
        const options=[...presets.map(p=>[p.id,p.label]),...(config.local.sprite?[['custom','Мой файл']]:[])];
        const signature=JSON.stringify(options);
        if($('symbol-preset').dataset.options!==signature){$('symbol-preset').replaceChildren(...options.map(([v,label])=>new Option(label,v)));$('symbol-preset').dataset.options=signature;}
        $('symbol-preset').value=config.local.symbolSource==='custom'&&config.local.sprite?'custom':config.preferences.symbolPresetId;
        $('symbol-file-name').textContent=config.local.sprite?.name??(config.local.sprite?'Ваше изображение сохранено в браузере':'');
        if($('twitch-channel').value!==config.preferences.twitchChannel)$('twitch-channel').value=config.preferences.twitchChannel;
        void refreshSymbols();
    }
    const subscriptions=[config.subscribe(update),store.subscribe(update)];
    const initialVersion=selectionVersion;
    config.local.loadSprite().then(blob=>{
        if(disposed||selectionVersion!==initialVersion)return;
        config.local.sprite=blob;config.emit();
    });
    update();
    return ()=>{disposed=true;loadVersion++;subscriptions.forEach(fn=>fn());bindings.forEach(fn=>fn());disposeSymbolSheet(sheet);};
}
