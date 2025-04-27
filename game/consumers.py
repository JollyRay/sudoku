import asyncio
import json
import logging
import os
from threading import Thread
from typing import Awaitable, Callable, Any
import requests
from random import random, randint
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.utils import IntegrityError

from .exception import SudokuException
from .stubs import UserInLobbyInfo
from .models import *
from .utils import AddHandler, SudokuBoarderProxy

from sudoku.settings import SECRET_WEBSOCKET_ADMIN_KEY_VALUE_BYTE, SECRET_WEBSOCKET_ADMIN_KEY_HEADER_BYTE


userRequestHandler = AddHandler()
bonusHandler = AddHandler()

class SudokuConsumer(AsyncWebsocketConsumer):

    async def _connect_admin(self) -> bool:
        for header_name, header_value in self.scope['headers']:
            if header_name == SECRET_WEBSOCKET_ADMIN_KEY_HEADER_BYTE:
                if SECRET_WEBSOCKET_ADMIN_KEY_VALUE_BYTE != header_value:
                    return False
                self.is_admin: bool = True
                self.room_code: str = f"sudoku_{self.scope['url_route']['kwargs'].get('room_name')}"
                await self.channel_layer.group_add(self.room_code, self.channel_name)
                await self.accept()
                return True
        return False

    async def connect(self) -> None:
        if await self._connect_admin():
            return
        # Set settings

        self.is_admin = False
        self.room_code = f"sudoku_{self.scope['url_route']['kwargs'].get('room_name')}"
        
        if not self.room_code:
            await self.close()
            return
        
        self.nick: str = self.scope['cookies'].get('nick')
        if not self.nick:
            await self.close()
            return

        self.is_twtich_channel: bool = False

        # Accept and add to group

        await self.channel_layer.group_add(self.room_code, self.channel_name)
        await self.accept()

        # Generate first data

        await self.send_full_data(kind = 'new_user', nick = self.nick)
        info_maps: dict[str, UserInLobbyInfo] = await database_sync_to_async(SudokuBoarderProxy.get_room_info)(self.room_code)
        await self.send(text_data = json.dumps({'kind': 'first_data', 'data': info_maps}))
        await self.add_channel()

    async def disconnect(self, close_code: int):
        
        try:
            if not self.is_admin:
                is_remove_lobby: bool = await database_sync_to_async(SudokuBoarderProxy.delete_user)(self.room_code, self.nick)

                if not is_remove_lobby:
                    await self.send_full_data(kind = 'disconection', nick = self.nick)
                else:
                    await self.channel_layer.group_send(
                        self.room_code, {'type': 'disconnect_lobby'}
                    )

            await self.channel_layer.group_discard(self.room_code, self.channel_name)

        except AttributeError:
            pass

    async def dispatch(self, message):
        try:
            await super().dispatch(message)
        except ValueError as err: 
            logging.error(err)

    async def receive(self, text_data: str):        

        text_data_json = json.loads(text_data)
        if not isinstance(text_data_json, dict):
            await self.close()
            return
        
        kind: str | None = text_data_json.get('kind')
        if kind is None:
            await self.close()
            return
        
        logging.info(f'WebSocket {kind} {self.scope["path"]} [{self.scope["client"][0]}:{self.scope["client"][1]}]')
        func: Callable[..., Awaitable[Any]] | None = userRequestHandler.reqest_type_map.get(kind)

        if func is None:
            return
        
        try:
            await func(self, **text_data_json)
        except SudokuException as e:
            logging.error(e)
            self.close()
        except TypeError:
            logging.warning(f'User did not provide all the arguments for function "{kind}"')

    async def send_full_data(self, **data: Any) -> None:
        await self.channel_layer.group_send(
            self.room_code, {'type': 'send_message', 'data': data}
        )
    
    async def send_message(self, data: dict[str, dict[str, Any]]) -> None:
        if self.is_admin: return
        await self.send(text_data = json.dumps(data.get('data')))

    async def disconnect_lobby(self, _: int) -> None:
        await self.send(text_data = json.dumps({'kind': 'lobby_remove'}))
        await self.close()

    #############################
    #                           #
    #      RECEVE FUNCTION      #
    #                           #
    #############################

    @userRequestHandler('generate')
    async def generate_sudoku(self, difficulty: str = 'medium', *args: Any, **kwargs: Any) -> None:

        can_add_board = await database_sync_to_async(SudokuBoarderProxy.add_random_board)(self.room_code, self.nick, difficulty, [*bonusHandler.reqest_type_map])
        if not can_add_board:
            await self.close()
            return

        clean_board = await database_sync_to_async(SudokuBoarderProxy.get_clean_board)(self.room_code, self.nick)
        bonus_map = await database_sync_to_async(SudokuBoarderProxy.get_bonus_map)(self.room_code, self.nick)
        time_from = await database_sync_to_async(SudokuBoarderProxy.get_time_from)(self.room_code, self.nick)

        await self.send_full_data(
            kind = 'board',
            to = self.nick,
            board = clean_board,
            bonus = bonus_map,
            time_from = time_from
        )

    @userRequestHandler('set_value')
    async def set_sudoku_value(self, cell_number: int, value: int, is_finish: bool, *args: Any, **kwargs: Any):

        # Protect if send None or empty string
        if not value:
            value = 0

        is_equal, bonus_name = await database_sync_to_async(SudokuBoarderProxy.set_value)(self.room_code, self.nick, value, cell_number)

        if is_equal is None:
            return
        
        extra_info: dict[str, Any] = {}
        if is_equal and bonus_name:

            extra_info['bonus_type'] = bonus_name
            extra_info['detale'] = await bonusHandler.reqest_type_map[bonus_name](self)

        if is_finish:
            finish_time = await database_sync_to_async(SudokuBoarderProxy.finish)(self.room_code, self.nick)
            if finish_time is not None:
                extra_info['is_finish'] = True
                extra_info['time_to'] = finish_time

        
        await self.send_full_data(
            kind = 'cell_result',
            cell_number = cell_number,
            value = value,
            to = self.nick,
            is_right = is_equal,
            **extra_info
        )

    @userRequestHandler('add_twitch_channel')
    async def add_twitch_channel(self, *args: Any, **kwargs: Any):
        if self.is_twtich_channel: return
        tempThread = Thread(target = asyncio.run, args = (self._add_twitch_channel(),))

        tempThread.start()
    
    async def _add_twitch_channel(self, *args: Any, **kwargs: Any):
        host = os.getenv('TWITCH_BOT_HOST')
        port = os.getenv('TWITCH_BOT_PORT')
        payload = {
            "is_add": True,
            "channel_name": self.nick,
            "room_code": self.room_code
        }
        try:
            respond = requests.post(f'http://{host}:{port}', json = payload)
            self.is_twtich_channel = respond.status_code == 200
            await self.send(text_data = json.dumps({'kind': 'is_add_twitch', 'ok': respond.status_code == 200}))
        except requests.exceptions.ConnectionError:
            logging.error(f'Connectiob error {host}:{port}')

    @userRequestHandler('admin_bonus')
    async def catch_admin_bonus(self, to, bonus_type, *args: Any, **kwargs: Any):

        if not self.is_admin:
            await self.close()
            return

        try:
            await self.send_full_data(
                kind = 'admin_bonus',
                to = to,
                bonus_type = bonus_type,
                detale = await bonusHandler.reqest_type_map[bonus_type](self)
            )
        except KeyError:
            logging.warning(f'Admin user unknow bonus "{bonus_type}"')

    #############################
    #                           #
    #          BONUS            #
    #                           #
    #############################

    @bonusHandler('SHADOW_BOX')
    async def generate_shadow_box_detale(self):
        return {'box': randint(0, 8)}
    
    @bonusHandler('SWAP')
    async def generate_swap_detale(self):
        is_row = random() > 0.5
        is_big = random() > 0.5
        first_index = randint(0, 2)
        second_index = ((first_index + 1) if random() > 0.5 else (first_index - 1)) % 3
        if not is_big:
            bais = randint(0, 2) * 3
            first_index += bais
            second_index += bais

        return {
            'is_row': is_row,
            'is_big': is_big,
            'first': first_index,
            'second': second_index
        }
    
    @bonusHandler('ROLL')
    async def generate_roll_box_detale(self):
        return {'box': randint(0, 8)}
    
    @bonusHandler('DANCE')
    async def generate_dance_detale(self):
        return {'box': randint(0, 8)}

    #############################
    #                           #
    #          DATABASE         #
    #                           #
    #############################

    @database_sync_to_async
    def add_channel(self) -> None:
        try:
            lobby = LobbySetting.objects.get_or_create(code = self.room_code)[0]
            UserSetting.objects.create(lobby = lobby, nick = self.nick)
        except IntegrityError:
            logging.error(f'User {self.nick} exist name.')
