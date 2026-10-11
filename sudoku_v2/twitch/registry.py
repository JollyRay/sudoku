import hashlib
import json
from time import time
from uuid import uuid4

from django.conf import settings
from common.redis import CommitGuard
from .commands import normalize_channel


class TwitchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code,self.message=code,message


class TwitchRegistry:
    def __init__(self, storage):
        self.storage,self.redis=storage,storage.redis

    @property
    def prefix(self):
        # Deliberately disjoint from every lobby prefix, including a lobby named twitch.
        return f"{getattr(settings,'SUDOKU_V2_PREFIX','sudoku-v2')}-global:twitch"

    def binding_key(self, channel):
        return f'{self.prefix}:binding:{normalize_channel(channel)}'

    def dedup_key(self, bot_id, channel, message_id):
        digest=hashlib.sha256(json.dumps([bot_id,channel,message_id]).encode()).hexdigest()
        return f'{self.prefix}:message:{digest}'

    @staticmethod
    def encode(binding):
        return {key:json.dumps(value) for key,value in binding.items()}

    @staticmethod
    def decode(raw):
        return {key:json.loads(value) for key,value in raw.items()} if raw else None

    async def get(self, channel):
        return self.decode(await self.redis.hgetall(self.binding_key(channel)))

    def status_key(self, binding):
        return f"{self.prefix}:status:{binding['bindingId']}"

    async def get_status(self, binding):
        value=await self.redis.get(self.status_key(binding))
        return json.loads(value) if value else None

    async def _prune(self, channel):
        key=self.binding_key(channel)
        for _ in range(8):
            binding=await self.get(channel)
            if not binding:return None
            lobby=binding['lobby'];epoch=await self.storage.get_room_epoch(lobby)
            if epoch==binding['roomEpoch'] and await self.storage.get_active_usernames(lobby):return binding
            result=await self.redis.compare_and_write_batch([
                CommitGuard(key,'hash',{'bindingId':json.dumps(binding['bindingId'])}),
                CommitGuard(self.storage._lobby_prefix(lobby)+':epoch','string',epoch),
            ],{key:{}},{})
            if result=='saved':return None
        return None

    async def list_active(self):
        bindings=[]
        for key in await self.redis.keys(self.prefix+':binding:*'):
            binding=await self._prune(key.rsplit(':',1)[1])
            if binding:bindings.append(binding)
        return sorted(bindings,key=lambda b:b['channel'])

    async def cleanup_lobby(self, lobby, epoch):
        for key in await self.redis.keys(self.prefix+':binding:*'):
            binding=self.decode(await self.redis.hgetall(key))
            if binding and binding['lobby']==lobby and binding['roomEpoch']==epoch:
                await self._prune(binding['channel'])

    async def register(self, lobby, owner, connection_id, channel, cooldown_seconds):
        try:channel=normalize_channel(channel)
        except ValueError as error:raise TwitchError('invalid_channel','Введите имя канала Twitch без ссылки.') from error
        if type(cooldown_seconds) is not int or not 0<=cooldown_seconds<=86400:
            raise TwitchError('invalid_cooldown','КД должен быть целым числом от 0 до 86400 секунд.')
        key=self.binding_key(channel)
        await self._prune(channel)
        for _ in range(16):
            if await self.storage.get_presence_token(lobby,owner)!=connection_id:
                raise TwitchError('connection_replaced','Подключитесь к комнате заново.')
            epoch=await self.storage.get_room_epoch(lobby)
            if not epoch:raise TwitchError('room_unavailable','Комната больше не существует.')
            raw=await self.redis.hgetall(key);current=self.decode(raw)
            if current and (current['lobby'],current['owner'],current['roomEpoch'])!=(lobby,owner,epoch):
                raise TwitchError('channel_in_use','Этот канал уже подключён другим игроком или к другой комнате.')
            binding={**current,'cooldownSeconds':cooldown_seconds} if current else {
                'bindingId':uuid4().hex,'channel':channel,'lobby':lobby,'owner':owner,'roomEpoch':epoch,
                'cooldownSeconds':cooldown_seconds,'registeredAt':int(time()*1000),'lastAppliedAt':None,
            }
            guards=[CommitGuard(key,'hash',raw or None),
                CommitGuard(self.storage._presence_key(lobby,owner),'string',connection_id),
                CommitGuard(self.storage._lobby_prefix(lobby)+':epoch','string',epoch)]
            if await self.redis.compare_and_write_batch(guards,{key:self.encode(binding)},{})=='saved':return binding
        raise TwitchError('binding_busy','Подключение обновляется. Попробуйте ещё раз.')

    async def disconnect(self, lobby, owner, connection_id, channel):
        try:key=self.binding_key(channel)
        except ValueError as error:raise TwitchError('invalid_channel','Неверный канал Twitch.') from error
        for _ in range(16):
            if await self.storage.get_presence_token(lobby,owner)!=connection_id:
                raise TwitchError('connection_replaced','Подключитесь к комнате заново.')
            raw=await self.redis.hgetall(key);binding=self.decode(raw)
            if not binding:return
            epoch=await self.storage.get_room_epoch(lobby)
            if (binding['lobby'],binding['owner'],binding['roomEpoch'])!=(lobby,owner,epoch):
                raise TwitchError('binding_forbidden','Отключить бота может только подключивший его игрок.')
            if await self.redis.compare_and_write_batch([
                CommitGuard(key,'hash',raw),CommitGuard(self.storage._presence_key(lobby,owner),'string',connection_id),
                CommitGuard(self.storage._lobby_prefix(lobby)+':epoch','string',epoch)],{key:{}},{})=='saved':return
        raise TwitchError('binding_busy','Подключение обновляется. Попробуйте ещё раз.')
