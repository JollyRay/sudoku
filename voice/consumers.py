from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.utils import IntegrityError
from django.db.models import F, QuerySet
from collections.abc import Callable, Awaitable
import asyncio
import json
from copy import copy
from time import time

from .models import VoiceGroup, VoiceMember
from .stubs import MemberNick, OfferData
from game.utils import AddHandler

user_request_handler = AddHandler()

class VoiceConsumer(AsyncWebsocketConsumer):

    name_locker = asyncio.Lock()
    user_number = int(time())
    user_nick_pattern = 'user_n%d'

    #############################
    #                           #
    #         CONECTION         #
    #                           #
    #############################

    async def websocket_connect(self, event):

        self.room_code: str = self.scope['url_route']['kwargs'].get('room_name')
        if not self.room_code:
            await self.close()
            return
        
        await self.accept()
    
    async def websocket_disconnect(self, event):
        print('Webscoket isconnected', event)
        await super().websocket_disconnect(event)

    async def disconnect(self, close_code):
        await self.delete_voice_member()
        await self.send_data_with_restrictions(sender = self.nick, type = 'bye')
        await self.channel_layer.group_discard(self.room_code, self.channel_name)
        print('Disconnected', close_code)

    async def dispatch(self, message):
        try:
            await super().dispatch(message)
        except ConnectionRefusedError as err: 
            print(err)

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

    async def send_data_with_restrictions(self, **data: str|bool):
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
            sdp_list: tuple[str|None, str|None, str|None] = (
                data['data'][self.nick]['sdpVoice'],
                data['data'][self.nick]['sdpScreenReceiver'],
                data['data'][self.nick]['sdpScreenProvider'],
            )
            sender = data['sender']
        except KeyError:
            return
        
        for index, sdp in enumerate(sdp_list):
            if sdp:
                usefull_data = {
                    'type': 'offer',
                    'sdp': sdp,
                    'isProvider': index == 1,
                    'isScreen': index > 0,
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

        if hasattr(self, 'nick'):
            await self.close()
            return
        
        async with VoiceConsumer.name_locker:
            VoiceConsumer.user_number += 1
            self.nick: str = VoiceConsumer.user_nick_pattern % VoiceConsumer.user_number

        is_add = await self._add_user()
        if not is_add:
            self.close()
            return


        members = await self.get_voice_members()
        await self.send(text_data = json.dumps(
            {
                'type': 'ready',
                'members': [{"nick": member['nick'], 'hasScreen': member['has_screen_sream']} for member in members], 'nick': self.nick}))

    @user_request_handler('reconnect')
    async def reconnect_handler(self, sender: str, hasScreen: bool, **_: str) -> None:
        if hasattr(self, 'nick'):
            await self.close()
            return
        
        self.nick = sender

        is_add = await self._add_user(hasScreen)
        if not is_add:
            self.close()
            return
        
        await self.send_data_with_restrictions(sender = self.nick, type = 'reconnect')

    async def _add_user(self, has_screen: bool = False) -> bool:
        is_add = await self.add_voice_member(has_screen)
        if not is_add:
            await self.send(text_data = json.dumps({'type': 'error_nick'}))
            return False
        await self.channel_layer.group_add(self.room_code, self.channel_name)
        return True

    @user_request_handler('offers')
    async def offers_handler(self, sender: str, data: str, **_: str) -> None:
        await self.channel_layer.group_send(
            self.room_code, {'type': 'send_offers', 'sender': sender, 'data': data}
        )

    @user_request_handler('answer')
    async def answer_handler(self, sdp: str, isScreen: bool, isProvider: bool, to: str, **_: str) -> None:
        await self.send_data_with_restrictions(sender = self.nick, sdp = sdp, isScreen = isScreen, isProvider = isProvider, to = to, type = 'answer')

    @user_request_handler('candidate')
    async def candidate_handler(self, candidate: str, sdpMid: str, isProvider: bool, isScreen: bool, to: str, sdpMLineIndex: str, **_: str) -> None:
        await self.send_data_with_restrictions(candidate = candidate, sdpMid = sdpMid, sdpMLineIndex = sdpMLineIndex, isScreen = isScreen, isProvider = isProvider, sender = self.nick, to = to, type = 'candidate')

    @user_request_handler('addScreen')
    async def add_screen(self, **_: str):
        await self.update_has_screen_stream(True)

    @user_request_handler('removeScreen')
    async def remove_screen(self, **_: str):
        await self.update_has_screen_stream(False)

    #############################
    #                           #
    #         DATABASE          #
    #                           #
    #############################

    @database_sync_to_async # type: ignore
    def add_voice_member(self, has_screen: bool) -> bool:
        voice_group, _ = VoiceGroup.objects.get_or_create(name = self.room_code)

        try: 
            VoiceMember.objects.create(nick = self.nick, voice_group = voice_group, has_screen_sream = has_screen)
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
        except (VoiceMember.DoesNotExist, AttributeError):
            return False
        
    @database_sync_to_async # type: ignore
    def get_voice_members(self) -> list[MemberNick]:

        return list(VoiceMember.objects.filter(voice_group__name = self.room_code).values('nick', 'has_screen_sream'))
        
    @database_sync_to_async # type: ignore
    def get_voice_group_size(self) -> int:

        return VoiceMember.objects.filter(voice_group__name = self.room_code).count()

    @database_sync_to_async # type: ignore
    def update_has_screen_stream(self, is_exist_screen: bool) -> bool:
        return VoiceMember.objects.filter(nick = self.nick).update(has_screen_sream = is_exist_screen) > 0