"""Read-only Twitch IRC transport. Never logs raw lines or credentials."""
import asyncio
import re
import ssl
from collections import deque
from dataclasses import dataclass
from time import monotonic

from .types import ExternalBonusCommand


class AuthError(Exception):
    def __init__(self): super().__init__('Twitch authentication failed')


@dataclass(frozen=True)
class IRCMessage:
    tags: dict[str, str]
    prefix: str | None
    command: str
    params: list[str]


def parse_irc_line(line):
    line=line.rstrip('\r\n')
    if not line or len(line)>16384 or '\r' in line or '\n' in line: return None
    tags={}; prefix=None
    if line.startswith('@'):
        raw,sep,line=line.partition(' ')
        if not sep: return None
        escapes={':':';','s':' ','\\':'\\','r':'\r','n':'\n'}
        for item in raw[1:].split(';'):
            key,_,value=item.partition('=')
            tags[key]=re.sub(r'\\(.)',lambda m:escapes.get(m[1],m[1]),value)
    line=line.lstrip()
    if line.startswith(':'):
        prefix,sep,line=line[1:].partition(' ')
        if not sep: return None
    head,sep,tail=line.partition(' :')
    parts=head.split()
    if not parts: return None
    return IRCMessage(tags,prefix,parts[0].upper(),parts[1:]+([tail] if sep else []))


class RateWindow:
    def __init__(self, limit, seconds, *, clock=monotonic):
        self.limit,self.seconds,self.clock=limit,seconds,clock
        self.entries=deque()

    def take(self):
        now=self.clock()
        while self.entries and self.entries[0]<=now-self.seconds: self.entries.popleft()
        if len(self.entries)>=self.limit: return False
        self.entries.append(now)
        return True


class TwitchIRCClient:
    def __init__(self, login, token, bot_id, *, connect=asyncio.open_connection,
                 reconcile_seconds=2, join_timeout=15, retry_seconds=1,
                 max_channels=100, join_limit=20, auth_limit=20, clock=monotonic):
        self.login,self.token,self.bot_id=login,token.removeprefix('oauth:'),bot_id
        self.connect,self.clock=connect,clock
        self.reconcile_seconds,self.join_timeout,self.retry_seconds=reconcile_seconds,join_timeout,retry_seconds
        self.max_channels=max_channels
        self.joins=RateWindow(join_limit,10,clock=clock)
        self.auths=RateWindow(auth_limit,10,clock=clock)

    async def run(self, channels_provider, on_message, on_status):
        delay=self.retry_seconds
        while True:
            try:
                while not self.auths.take(): await asyncio.sleep(.1)
                await self._session(channels_provider,on_message,on_status)
            except AuthError:
                for binding in await channels_provider(): await on_status(binding,'auth_error','authentication')
                raise
            except (OSError, ValueError, asyncio.TimeoutError, ConnectionError):
                for binding in await channels_provider(): await on_status(binding,'error','connection')
            await asyncio.sleep(delay)
            delay=min(30,delay*2)

    async def _session(self, provider, on_message, on_status):
        reader,writer=await asyncio.wait_for(self.connect('irc.chat.twitch.tv',6697,
            ssl=ssl.create_default_context(),limit=16384),10)
        self.writer=writer
        self.subscriptions={}
        used_channels=set()
        self.authenticated=asyncio.Event()
        self.connected_at=self.clock()

        async def send(line):
            writer.write((line+'\r\n').encode())
            await asyncio.wait_for(writer.drain(),10)

        async def reconcile():
            while True:
                bindings={b['channel']:b for b in await provider()}
                for channel in list(self.subscriptions):
                    old=self.subscriptions[channel]
                    current=bindings.get(channel)
                    if current is None:
                        await send('PART #'+channel)
                        del self.subscriptions[channel]
                    elif old['binding']['bindingId']!=current['bindingId']:
                        # An old JOIN acknowledgement cannot be associated with a new binding.
                        # A fresh TCP stream fences all old transport acknowledgements.
                        raise ConnectionError('Binding replaced')
                    else: old['binding']=current
                if not self.authenticated.is_set():
                    if self.clock()-self.connected_at>self.join_timeout: raise ConnectionError('Authentication timeout')
                    for binding in bindings.values(): await on_status(binding,'connecting','authentication')
                else:
                    for channel,binding in bindings.items():
                        subscription=self.subscriptions.get(channel)
                        if subscription:
                            if subscription['state']=='connecting' and self.clock()-subscription['sent']>=self.join_timeout:
                                subscription['state']='error';subscription['reason']='join_timeout'
                            await on_status(binding,subscription['state'],subscription.get('reason',''))
                        elif len(self.subscriptions)>=self.max_channels:
                            await on_status(binding,'error','channel_limit')
                        elif channel in used_channels:
                            raise ConnectionError('Channel rebound after PART')
                        elif not self.joins.take():
                            await on_status(binding,'connecting','rate_limit')
                        else:
                            self.subscriptions[channel]={'binding':binding,'sent':self.clock(),'state':'connecting'}
                            used_channels.add(channel)
                            await on_status(binding,'connecting','join')
                            await send('JOIN #'+channel)
                await asyncio.sleep(self.reconcile_seconds)

        async def read():
            while True:
                raw=await asyncio.wait_for(reader.readline(),180)
                if not raw: raise ConnectionError('Closed')
                if len(raw)>16384 or not raw.endswith(b'\r\n'): raise ConnectionError('Invalid IRC line')
                message=parse_irc_line(raw.decode('utf-8',errors='replace'))
                if message is None: continue
                if message.command=='PING':
                    await send('PONG :'+(message.params[-1] if message.params else ''))
                    continue
                if message.command=='RECONNECT': raise ConnectionError('Reconnect requested')
                if message.command=='001': self.authenticated.set(); continue
                if message.command=='NOTICE' and any('authentication failed' in p.lower() or 'improperly formatted auth' in p.lower() for p in message.params):
                    raise AuthError()
                channel=next((p[1:].lower() for p in message.params if p.startswith('#')),None)
                subscription=self.subscriptions.get(channel)
                if not subscription: continue
                own=(message.prefix or '').split('!',1)[0].lower()==self.login
                if message.command=='ROOMSTATE' or message.command=='366' or (message.command=='JOIN' and own):
                    subscription['state']='connected';subscription['reason']=''
                    await on_status(subscription['binding'],'connected','')
                elif message.command=='NOTICE' or (message.command=='PART' and own):
                    subscription['state']='error';subscription['reason']='channel_unavailable'
                    await on_status(subscription['binding'],'error','channel_unavailable')
                elif message.command=='PRIVMSG' and subscription['state']=='connected' and len(message.params)==2:
                    tags=message.tags
                    if own or tags.get('user-id')==self.bot_id or not tags.get('id') or not tags.get('user-id'): continue
                    timestamp=tags.get('tmi-sent-ts','')
                    if not timestamp.isdecimal(): continue
                    command=ExternalBonusCommand('twitch_chat',tags['id'],channel,tags['user-id'],int(timestamp),message.params[1])
                    await on_message(command,subscription['binding'])

        tasks=[]
        try:
            await send('PASS oauth:'+self.token)
            await send('NICK '+self.login)
            await send('CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands')
            tasks=[asyncio.create_task(read()),asyncio.create_task(reconcile())]
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done: task.result()
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            writer.close()
            try: await asyncio.wait_for(writer.wait_closed(),2)
            except (OSError,asyncio.TimeoutError): pass
