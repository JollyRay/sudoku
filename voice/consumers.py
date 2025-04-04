from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import F
from collections.abc import Callable, Awaitable
import asyncio
import json

from .models import VoiceGroupSize
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
        size = await self.update_group_size(1)

        await self.send(text_data = json.dumps({'type': 'hello', 'nick': self.nick}))
        if size > 1:
            await self.send(text_data = json.dumps({'type': 'ready'}))

    
    async def websocket_disconnect(self, event):
        await self.update_group_size(-1)
        print('Disconnected', event)

    async def disconnect(self, close_code):
        print('Close')

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
        usefull_data = data['data']

        if self.nick == usefull_data.get('sender'):
            return
        if usefull_data.get('to'):
            if usefull_data.get('to') != self.nick:
                return
        else:
            usefull_data['to'] = self.nick

        await self.send(text_data = json.dumps(usefull_data))

    #############################
    #                           #
    #      MESSAGE HANDLER      #
    #                           #
    #############################

    @user_request_handler('offer')
    async def offer_handler(self, sdp: str, *args: str, **kwargs: str) -> None:
        await self.send_data_with_restrictions(sender = self.nick, sdp = sdp, type = 'offer')

    @user_request_handler('answer')
    async def answer_handler(self, sdp: str, to: str, *args: str, **kwargs: str) -> None:
        await self.send_data_with_restrictions(sender = self.nick, sdp = sdp, to = to, type = 'answer')

    @user_request_handler('candidate')
    async def candidate_handler(self, candidate: str, sdpMid: str, sdpMLineIndex: str, *args: str, **kwargs: str) -> None:
        await self.send_data_with_restrictions(candidate = candidate, sdpMid = sdpMid, sdpMLineIndex = sdpMLineIndex, sender = self.nick, type = 'candidate')

    # @userRequestHandler('bye')
    # async def bye_handler(self, sender: str, *args, **kwargs) -> None:
    #     await self.send_data_with_restrictions(sender = sender, type = 'bye')

    #############################
    #                           #
    #         DATABASE          #
    #                           #
    #############################

    @database_sync_to_async # type: ignore
    def update_group_size(self, delta: int) -> int:
        VoiceGroupSize.objects.filter(name=self.room_code).update(size=F('size') + delta)

        voice_group_size, _ = VoiceGroupSize.objects.get_or_create(
            name=self.room_code,
        )

        if not voice_group_size.size:
            voice_group_size.delete()
            return 0
        
        return voice_group_size.size
