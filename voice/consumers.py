from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.utils import IntegrityError
from django.db.models import F, QuerySet
from collections.abc import Callable, Awaitable
import asyncio
import json
from copy import copy

from .models import VoiceGroup, VoiceMember
from .stubs import MemberNick, OfferData
from game.utils import AddHandler

user_request_handler = AddHandler()

class VoiceConsumer(AsyncWebsocketConsumer):

    name_locker = asyncio.Lock()
    user_number = 0
    user_nick_pattern = 'user_n%d'

    #############################
    #                           #
    #         CONECTION         #
    #                           #
    #############################

    async def websocket_connect(self, event):

        async with VoiceConsumer.name_locker:
            VoiceConsumer.user_number += 1
            self.nick: str = VoiceConsumer.user_nick_pattern % VoiceConsumer.user_number

        self.room_code: str = self.scope['url_route']['kwargs'].get('room_name')
        if not self.room_code:
            await self.close()
            return
        
        await self.channel_layer.group_add(self.room_code, self.channel_name)
        await self.accept()

        is_add = await self.add_voice_member()
        if not is_add:
            await self.send(text_data = json.dumps({'type': 'error_nick'}))
            self.close()

    
    async def websocket_disconnect(self, event):
        print('Webscoket isconnected', event)
        await super().websocket_disconnect(event)

    async def disconnect(self, close_code):
        await self.delete_voice_member()
        await self.send_data_with_restrictions(sender = self.nick, type = 'bye')
        await self.channel_layer.group_discard(self.room_code, self.channel_name)
        print('Disconnected', close_code)

    #############################
    #                           #
    #        FOR MESSAGE        #
    #                           #
    #############################

    async def websocket_receive(self, event):
        print(event['text'])
        try:
            text_data_json = json.loads(event['text'])
            if not isinstance(text_data_json, dict):
                return
            
            kind = text_data_json['type']
            
            # logging.info(f'WebSocket {kind} {self.scope["path"]} [{self.scope["client"][0]}:{self.scope["client"][1]}]')
            func: Callable[..., Awaitable[None]] = user_request_handler.reqest_type_map[kind]
            
            await func(self, **text_data_json)
        except (KeyError, IndexError, TypeError) as e:
            print(e)

    async def send_data_with_restrictions(self, **data: str):
        await self.channel_layer.group_send(
            self.room_code, {'type': 'send_message_with_exclude_self', 'data': data}
        )
    
    async def send_message_with_exclude_self(self, data: dict[str, dict[str, str]]) -> None:
        usefull_data = copy(data['data'])

        if self.nick == usefull_data.get('sender'):
            return
        if usefull_data.get('to'):
            if usefull_data['to'] != self.nick:
                return
        else:
            usefull_data['to'] = self.nick

        await self.send(text_data = json.dumps(usefull_data))

    async def send_offers(self, data: OfferData):
        
        try:
            sdp: str = data['data'][self.nick]
            sender: str = data['sender']
        except KeyError:
            return
        
        usefull_data = {
            'type': 'offer',
            'sdp': sdp,
            'sender': sender,
            'to': self.nick,
        }
        await self.send(text_data = json.dumps(usefull_data))

    #############################
    #                           #
    #      MESSAGE HANDLER      #
    #                           #
    #############################

    @user_request_handler('ready')
    async def ready_handler(self, **_: str) -> None:
        members = await self.get_voice_members()
        await self.send(text_data = json.dumps({'type': 'ready', 'members': [member['nick'] for member in members], 'nick': self.nick}))

    @user_request_handler('offers')
    async def offers_handler(self, sender: str, data: str, **_: str) -> None:
        await self.channel_layer.group_send(
            self.room_code, {'type': 'send_offers', 'sender': sender, 'data': data}
        )

    @user_request_handler('answer')
    async def answer_handler(self, sdp: str, to: str, **_: str) -> None:
        await self.send_data_with_restrictions(sender = self.nick, sdp = sdp, to = to, type = 'answer')

    @user_request_handler('candidate')
    async def candidate_handler(self, candidate: str, sdpMid: str, to: str, sdpMLineIndex: str, **_: str) -> None:
        await self.send_data_with_restrictions(candidate = candidate, sdpMid = sdpMid, sdpMLineIndex = sdpMLineIndex, sender = self.nick, to = to, type = 'candidate')

    #############################
    #                           #
    #         DATABASE          #
    #                           #
    #############################

    @database_sync_to_async # type: ignore
    def add_voice_member(self) -> bool:
        voice_group, _ = VoiceGroup.objects.get_or_create(name = self.room_code)

        try: 
            VoiceMember.objects.create(nick = self.nick, voice_group = voice_group)
            return True
        except IntegrityError:
            return False
        
    @database_sync_to_async # type: ignore
    def delete_voice_member(self) -> bool:

        try: 
            VoiceMember.objects.get(nick = self.nick, voice_group__name = self.room_code).delete()
            count = VoiceMember.objects.filter(voice_group__name = self.room_code).count()

            if not count:
                VoiceGroup.objects.get(name = self.room_code).delete()

            return True
        except VoiceMember.DoesNotExist:
            return False
        
    @database_sync_to_async # type: ignore
    def get_voice_members(self) -> list[MemberNick]:

        return list(VoiceMember.objects.filter(voice_group__name = self.room_code).values('nick'))
        
    @database_sync_to_async # type: ignore
    def get_voice_group_size(self) -> int:

        return VoiceMember.objects.filter(voice_group__name = self.room_code).count()

