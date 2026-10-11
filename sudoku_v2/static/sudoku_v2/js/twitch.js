const STATUS={disabled:'Бот не запущен',connecting:'Подключение…',connected:'Подключён',auth_error:'Ошибка авторизации бота',error:'Ошибка подключения'};
const REASON={join_timeout:'Twitch не подтвердил канал. Проверьте название и переподключите его.',
    channel_limit:'Достигнут лимит каналов бота.',rate_limit:'Ожидаем разрешённого времени подключения.',
    authentication:'Оператору нужно проверить OAuth бота.',connection:'Бот восстанавливает связь с Twitch.',
    channel_unavailable:'Twitch сообщил, что канал недоступен.',validation_unavailable:'Не удалось проверить авторизацию Twitch.'};

export function mountTwitchSettings(root,{network,config}) {
    const $=id=>root.querySelector(`#${id}`),bindings=[];
    let disposed=false,busy=false,reading=false,wasReady=false,message='',refreshError='',signature='';
    const bind=(el,event,fn)=>{el.addEventListener(event,fn);bindings.push(()=>el.removeEventListener(event,fn));};
    const selected=()=>config.runtime.twitch.bindings.find(b=>b.channel===$('twitch-channel').value.trim().toLowerCase());
    const refresh=async()=>{
        if(disposed||reading||busy||!config.runtime.ready)return;
        reading=true;
        try{await network.getTwitchStatus();if(!disposed){refreshError='';render();}}
        catch(error){if(!disposed){refreshError=error.message;render();}}
        finally{reading=false;}
    };
    const mutate=async action=>{
        if(busy||disposed||!config.runtime.ready)return;
        busy=true;message='';refreshError='';render();
        try{await action();}catch(error){if(!disposed)message=error.message;}
        finally{busy=false;if(!disposed)render();}
    };
    bind($('twitch-channel'),'input',e=>{message='';config.setPreference('twitchChannel',e.target.value);render();});
    bind($('twitch-cooldown'),'input',e=>{
        const value=e.target.valueAsNumber;
        if(Number.isInteger(value)&&value>=0&&value<=86400)config.setPreference('twitchCooldown',value);
    });
    bind($('twitch-connect'),'click',()=>{
        const channel=$('twitch-channel').value.trim(),cooldown=$('twitch-cooldown').valueAsNumber;
        if(!/^[a-z0-9_]{1,25}$/i.test(channel)){message='Введите имя канала без ссылки и #.';render();return;}
        if(!Number.isInteger(cooldown)||cooldown<0||cooldown>86400){message='КД: целое число от 0 до 86400 секунд.';render();return;}
        void mutate(()=>network.connectTwitch(channel,cooldown));
    });
    bind($('twitch-disconnect'),'click',()=>{const binding=selected();if(binding?.owner===config.username)void mutate(()=>network.disconnectTwitch(binding.channel));});
    bind($('twitch-refresh'),'click',()=>{message='';refreshError='';void refresh();});
    bind($('twitch-bindings'),'click',e=>{
        const button=e.target.closest('[data-twitch-channel]');if(!button)return;
        const binding=config.runtime.twitch.bindings.find(b=>b.channel===button.dataset.twitchChannel);
        if(binding){config.setPreference('twitchChannel',binding.channel);config.setPreference('twitchCooldown',binding.cooldownSeconds);}
    });
    function render(){
        const ready=config.runtime.ready;
        const becameReady=ready&&!wasReady;wasReady=ready;
        if($('twitch-channel').value!==config.preferences.twitchChannel)$('twitch-channel').value=config.preferences.twitchChannel;
        if(document.activeElement!==$('twitch-cooldown'))$('twitch-cooldown').value=config.preferences.twitchCooldown;
        const binding=selected(),foreign=binding&&binding.owner!==config.username;
        $('twitch-connect').textContent=busy?'Сохраняем…':binding?'Обновить КД':'Подключить';
        $('twitch-connect').disabled=busy||!ready||Boolean(foreign);
        $('twitch-disconnect').disabled=busy||!ready||!binding||Boolean(foreign);
        $('twitch-refresh').disabled=busy||!ready;
        $('twitch-channel').disabled=busy;$('twitch-cooldown').disabled=busy||Boolean(foreign);
        $('twitch-status').textContent=!ready?'Нет связи с игровым сервером':binding?
            `${STATUS[binding.status]??binding.status} · ${binding.channel} · КД ${binding.cooldownSeconds} с`:'Канал не подключён';
        $('twitch-owner').textContent=binding?`Подключил: ${binding.owner}${foreign?' · Управление доступно владельцу':''}`:'';
        const hint=message||refreshError||(binding?REASON[binding.reason]:'');
        $('twitch-message').textContent=hint??'';$('twitch-message').hidden=!hint;
        const next=JSON.stringify(config.runtime.twitch.bindings);
        if(next!==signature){
            signature=next;
            $('twitch-bindings').replaceChildren(...config.runtime.twitch.bindings.map(b=>{
                const button=document.createElement('button');button.type='button';button.dataset.twitchChannel=b.channel;
                button.textContent=`${b.channel} · ${b.owner} · ${STATUS[b.status]??b.status} · ${b.cooldownSeconds} с`;
                return button;
            }));
        }
        if(becameReady)void refresh();
    }
    const unsubscribe=config.subscribe(reason=>{if(reason==='twitch')refreshError='';render();}),timer=setInterval(()=>void refresh(),10000);
    render();
    return ()=>{disposed=true;clearInterval(timer);unsubscribe();bindings.forEach(fn=>fn());};
}
