function defaultUrl() {
    return `${location.protocol === 'https:'?'wss:':'ws:'}//${location.host}/ws/sudoku-v2/`;
}
export function connectWebsocket({store,config,url=defaultUrl(),WebSocketClass=WebSocket,reconnect=true,
    returnToJoin=()=>location.replace('/sudoku-v2/')}) {
    let socket, retryTimer, requestTimer, disposed=false, attempts=0, contextVersion=null;
    // Only tracks replies to already sent moves; disconnected edits are never queued.
    const sentEdits=[];
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
                if(kind==='board_data' || kind==='set_value') {
                    const own=data.board?.name===config.username;
                    const acknowledgedEdit=own && kind==='set_value'?sentEdits.shift():undefined;
                    if(data.config?.username===config.username){clearRequests();config.runtime.ready=true;attempts=0;}
                    else if(own && kind==='board_data')config.runtime.pending=false;
                    store.applySnapshot(data,acknowledgedEdit);watchRequests();
                    config.emit();flushContext();
                } else if(kind==='participants_data') {
                    store.applySnapshot(data);
                } else if(kind==='context_data') {
                    config.ackContext(data.config,contextVersion??-1);contextVersion=null;flushContext();
                } else if(kind==='error') {
                    if(data.code==='stale_context') {
                        contextVersion=null;config.runtime.ready=false;send('get_board_data');
                    } else if(data.code==='invalid_context') contextVersion=null;
                    else {
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
            clearRequests();contextVersion=null;
            if(event.code===4409){status('closed');returnToJoin();return;}
            if(event.code===4401){status('closed','Войдите в комнату заново.');return;}
            status('offline','Связь прервалась. Восстанавливаем соединение…');
            if(reconnect)retryTimer=setTimeout(open,Math.min(15000,1000*2**attempts++));
        });
    };
    const unsubscribe=config.subscribe(reason=>{if(reason==='preferences')flushContext();});
    const api={
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
        dispose(){disposed=true;clearTimeout(retryTimer);clearRequests();unsubscribe();socket?.close();},
    };
    open();return api;
}
