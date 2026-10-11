function defaultUrl() {
    return `${location.protocol === 'https:'?'wss:':'ws:'}//${location.host}/ws/sudoku-v2/`;
}
export function connectWebsocket({store,config,url=defaultUrl(),WebSocketClass=WebSocket,reconnect=true,
    returnToJoin=()=>location.replace('/sudoku-v2/'),twitchTimeoutMs=10000}) {
    let socket, retryTimer, requestTimer, contextRetryTimer, disposed=false, attempts=0, contextVersion=null;
    // Only tracks replies to already sent moves; disconnected edits are never queued.
    const sentEdits=[];
    const twitchRequests=new Map();let twitchSequence=0,lastTwitchSequence=0;
    const twitchKinds=new Set(['connect_twitch','disconnect_twitch','get_twitch_status']);
    const rejectTwitch=()=>{
        for(const request of twitchRequests.values()){clearTimeout(request.timer);request.reject(new Error('Нет связи с сервером'));}
        twitchRequests.clear();
    };
    const requestTwitch=(kind,data={})=>new Promise((resolve,reject)=>{
        if(disposed || !config.runtime.ready){reject(new Error('Нет связи с сервером'));return;}
        const sequence=++twitchSequence,requestId=`tw-${sequence}`;
        const timer=setTimeout(()=>{twitchRequests.delete(requestId);reject(new Error('Ответ Twitch задерживается. Обновите статус.'));},twitchTimeoutMs);
        twitchRequests.set(requestId,{resolve,reject,timer,sequence});
        try{send(kind,{...data,requestId});}catch(error){clearTimeout(timer);twitchRequests.delete(requestId);reject(error);}
    });
    const receiveTwitch=(kind,data)=>{
        const request=data.requestId?twitchRequests.get(data.requestId):null;
        if(data.requestId && !request)return;
        if(request){clearTimeout(request.timer);twitchRequests.delete(data.requestId);}
        if(kind==='error'){request?.reject(new Error(data.message??'Не удалось выполнить действие Twitch.'));return;}
        if(Array.isArray(data.bindings) && (!request || request.sequence>=lastTwitchSequence)
            && (data.serverNow??0)>=config.runtime.twitch.serverNow){
            if(request)lastTwitchSequence=request.sequence;
            config.runtime.twitch=data;config.emit('twitch');
        }
        request?.resolve(data);
    };
    const status=(value,message='')=>{
        config.runtime.status=value;config.runtime.message=message;
        if(value!=='connected')config.runtime.ready=false;
        config.emit();
    };
    const send=(kind,data={})=>{
        if(!socket || socket.readyState!==1)throw new Error('Нет подключения к серверу');
        socket.send(JSON.stringify({kind,data}));
    };
    const flushContext=()=>{
        if(!config.runtime.ready || contextVersion!==null || !config.dirtyPreferences.size)return;
        clearTimeout(contextRetryTimer);
        contextVersion=config.preferenceVersion;
        send('set_context',{...config.toSendableContext(),generationId:store.getBoard(config.username)?.generationId??null});
    };
    const clearRequests=()=>{
        clearTimeout(requestTimer);sentEdits.length=0;config.runtime.pending=false;
    };
    const watchRequests=()=>{
        clearTimeout(requestTimer);
        if(!sentEdits.length && !config.runtime.pending)return;
        requestTimer=setTimeout(()=>{
            clearRequests();status('offline','Ответ задерживается. Восстанавливаем состояние…');
            socket.close();
        },10000);
    };
    const connectionFailed=error=>{
        clearRequests();status('offline',error.message);socket.close();
    };
    const open=()=>{
        if(disposed)return;
        const current=new WebSocketClass(url);socket=current;
        status('connecting');
        current.addEventListener('open',()=>{
            if(disposed || current!==socket)return;
            contextVersion=null;send('get_board_data');status('connected');
        });
        current.addEventListener('message',event=>{
            if(disposed || current!==socket)return;
            try {
                const {kind,data={}}=JSON.parse(event.data);
                if(kind==='twitch_status' || (kind==='error' && twitchKinds.has(data.requestKind))) {
                    receiveTwitch(kind,data);
                } else if(kind==='board_data' || kind==='set_value') {
                    const own=data.board?.name===config.username;
                    const acknowledgedEdit=own && kind==='set_value'?sentEdits.shift():undefined;
                    if(data.config?.username===config.username){clearRequests();config.runtime.ready=true;attempts=0;}
                    else if(own && kind==='board_data')config.runtime.pending=false;
                    store.applySnapshot(data,acknowledgedEdit);watchRequests();
                    config.emit();flushContext();
                } else if(kind==='participants_data') {
                    store.applySnapshot(data);
                } else if(kind==='bonus_applied') {
                    store.applyBonusEvent(data);
                } else if(kind==='context_data') {
                    config.ackContext(data.config,contextVersion??-1);contextVersion=null;flushContext();
                } else if(kind==='error') {
                    if(data.requestKind==='set_context' || ['stale_context','invalid_context'].includes(data.code)) {
                        contextVersion=null;
                        if(data.code==='stale_context') {
                            config.runtime.ready=false;send('get_board_data');
                        } else if(data.code==='board_busy') {
                            clearTimeout(contextRetryTimer);
                            contextRetryTimer=setTimeout(flushContext,250);
                        }
                    } else if(data.requestKind==='generate_board') {
                        config.runtime.pending=false;watchRequests();
                    } else if(!data.requestKind || data.requestKind==='set_value') {
                        if(sentEdits.length)store.applySnapshot({},sentEdits.shift());
                        else config.runtime.pending=false;
                        watchRequests();
                    }
                    config.runtime.message=data.message??'Не удалось выполнить действие. Попробуйте ещё раз.';
                    config.emit();
                    if(data.code==='stale_generation'){config.runtime.ready=false;send('get_board_data');}
                }
            } catch {
                config.runtime.message='Не удалось прочитать ответ сервера. Обновите страницу.';config.emit();
            }
        });
        current.addEventListener('close',event=>{
            if(disposed || current!==socket)return;
            clearRequests();rejectTwitch();clearTimeout(contextRetryTimer);contextVersion=null;
            if(event.code===4409){status('closed');returnToJoin();return;}
            if(event.code===4401){status('closed','Войдите в комнату заново.');return;}
            status('offline','Связь прервалась. Восстанавливаем соединение…');
            if(reconnect)retryTimer=setTimeout(open,Math.min(15000,1000*2**attempts++));
        });
    };
    const unsubscribe=config.subscribe(reason=>{if(reason==='preferences')flushContext();});
    const api={
        connectTwitch:(channel,cooldownSeconds=0)=>requestTwitch('connect_twitch',{channel,cooldownSeconds}),
        disconnectTwitch:channel=>requestTwitch('disconnect_twitch',{channel}),
        getTwitchStatus:()=>requestTwitch('get_twitch_status'),
        sendCellValue(boardName,generationId,cellIndex,value) {
            if(disposed || config.runtime.status==='closed' || config.runtime.pending)return false;
            const edit=store.editCell(cellIndex,value);
            if(config.runtime.ready && socket?.readyState===1) {
                try {
                    send('set_value',{boardName,generationId,cellIndex,value});
                    sentEdits.push(edit);watchRequests();
                } catch(error){connectionFailed(error);}
            }
            return true;
        },
        requestBoardGeneration(difficulty,size=9) {
            if(!config.runtime.ready || config.runtime.pending)return false;
            config.runtime.pending=true;config.runtime.message='';config.emit();
            try {send('generate_board',{difficulty,size});watchRequests();return true;}
            catch(error){connectionFailed(error);return false;}
        },
        dispose(){disposed=true;clearTimeout(retryTimer);clearTimeout(contextRetryTimer);clearRequests();rejectTwitch();unsubscribe();socket?.close();},
    };
    open();return api;
}
