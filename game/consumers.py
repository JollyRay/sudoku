import asyncio
import json
import logging
import os
from threading import Thread
import requests
from random import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.utils import IntegrityError

from .models import *
from sudoku.settings import SECRET_WEBSOCKET_ADMIN_KEY_VALUE_BYTE, SECRET_WEBSOCKET_ADMIN_KEY_HEADER_BYTE

from .utils import AddHandler, convert_clean_board_to_map, create_bonus_map, SudokuMap

userRequestHandler = AddHandler()
bonusHandler = AddHandler()

class SudokuConsumer(AsyncWebsocketConsumer):

    async def _connect_admin(self) -> bool:
        for header_name, header_value in self.scope['headers']:
            if header_name == SECRET_WEBSOCKET_ADMIN_KEY_HEADER_BYTE:
                if SECRET_WEBSOCKET_ADMIN_KEY_VALUE_BYTE != header_value:
                    return False
                self.is_admin = True
                self.room_code = self.scope['url_route']['kwargs'].get('room_name')
                await self.channel_layer.group_add(self.room_code, self.channel_name)
                await self.accept()
                return True
        return False

    async def connect(self):
        if await self._connect_admin():
            return
        # Set settings

        self.is_admin = False
        self.room_code = self.scope['url_route']['kwargs'].get('room_name')
        # self.room_code = self.scope['session'].get('room_code')
        if not self.room_code:
            await self.close()
            return
        
        self.nick = self.scope['cookies'].get('nick')
        if not self.nick:
            await self.close()
            return
        
        self.is_first = self.scope['session'].get('is_first')
        self.solution_id = []

        # Accept and add to group

        await self.channel_layer.group_add(self.room_code, self.channel_name)
        await self.accept()

        # Generate first data

        await self.send_full_data(kind = 'new_user', nick = self.nick)
        info_maps = SudokuMap.get_by_room_info_type(self.room_code)
        await self.send(text_data = json.dumps({'kind': 'first_data', 'data': info_maps}))
        SudokuMap.set(self.room_code, self.nick)
        await self.add_channel()

    async def disconnect(self, close_code):
        try:
            if not self.is_admin:
                SudokuMap.remove(self.room_code, self.nick)

                is_remove_lobby = await self.delete_channel()

                if not is_remove_lobby:
                    await self.send_full_data(kind = 'disconection', nick = self.nick)
                else:
                    await self.send_full_data(kind = 'lobby_remove')

            await self.channel_layer.group_discard(self.room_code, self.channel_name)

        except AttributeError:
            pass

    async def dispatch(self, message):
        try:
            await super().dispatch(message)
        except ValueError: 
            print('Erroe ignore')

    async def receive(self, text_data):
        

        text_data_json = json.loads(text_data)
        if not isinstance(text_data_json, dict):
            await self.close()
            return
        
        kind = text_data_json.get('kind')
        if kind is None:
            await self.close()
            return
        
        print(f'WebSocket {kind} {self.scope["path"]} [{self.scope["client"][0]}:{self.scope["client"][1]}]')
        func = userRequestHandler.reqest_type_map.get(kind)

        if func is None:
            return
        
        await func(self, **text_data_json)

    async def send_full_data(self, **data):
        await self.channel_layer.group_send(
            self.room_code, {'type': 'send_message', 'data': data}
        )
    
    async def send_message(self, data):
        if self.is_admin: return
        await self.send(text_data = json.dumps(data.get('data')))

    #############################
    #                           #
    #      RECEVE FUNCTION      #
    #                           #
    #############################

    @userRequestHandler('generate')
    async def generate_sudoku(self, difficulty = 'medium', *args, **kwargs):

        boards = await self.get_random_board(difficulty)
        if boards is None:
            await self.close()
            return

        solution_board, clean_board = boards
        bonus_map = create_bonus_map(clean_board, [*bonusHandler.reqest_type_map])

        SudokuMap.set(self.room_code, self.nick, clean_board, solution_board, bonus_map)
        self.solution_id.append(solution_board[0].board_id)
        bonus_map = SudokuMap.get_bonus_for_send(self.room_code, self.nick)

        info_board = convert_clean_board_to_map(clean_board)
        await self.send_full_data(kind = 'board', to = self.nick, board = info_board, bonus = bonus_map)

    @userRequestHandler('set_value')
    async def set_sudoku_value(self, cell_number: int, value: int, *args, **kwargs):

        # Protect if send None or empty string
        if not value:
            value = 0

        is_equal = await database_sync_to_async(SudokuMap.equival)(self.room_code, self.nick, value, cell_number)

        if is_equal is None:
            return
        
        if is_equal:
            bonus_name = SudokuMap.pop_bonus(self.room_code, self.nick, cell_number)
            if bonus_name:
                await self.send_full_data(
                    kind = 'cell_result',
                    cell_number = cell_number,
                    value = value,
                    to = self.nick,
                    is_right = is_equal,
                    bonus_type = bonus_name,
                    detale = await bonusHandler.reqest_type_map[bonus_name](self)
                )
                return

        
        await self.send_full_data(
            kind = 'cell_result',
            cell_number = cell_number,
            value = value,
            to = self.nick,
            is_right = is_equal
        )

    @userRequestHandler('add_twitch_channel')
    async def add_twitch_channel(self, channel_name: str, *args, **kwargs):
        if not self.is_first: return
        tempThread = Thread(target = asyncio.run, args = (self._add_twitch_channel(channel_name),))

        tempThread.start()
    
    async def _add_twitch_channel(self, channel_name: str, *args, **kwargs):
        host = os.getenv('TWITCH_BOT_HOST')
        port = os.getenv('TWITCH_BOT_PORT')
        payload = {
            "is_add": True,
            "channel_name": channel_name,
            "room_code": self.room_code
        }
        try:
            respond = requests.post(f'http://{host}:{port}', json = payload)
            await self.send(text_data = json.dumps({'kind': 'is_add_twitch', 'ok': respond.status_code == 200}))
        except requests.exceptions.ConnectionError:
            print(f'Connectiob error {host}:{port}')

    @userRequestHandler('admin_bonus')
    async def catch_admin_bonus(self, to, bonus_type, *args, **kwargs):

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
    async def generate_roll_box_detale(self):
        return {'box': randint(0, 8)}
    
    @bonusHandler('SWAP')
    async def generate_roll_box_detale(self):
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

    #############################
    #                           #
    #          DATABASE         #
    #                           #
    #############################

    @database_sync_to_async
    def add_channel(self):
        try:
            lobby = LobbySetting.objects.get_or_create(code = self.room_code)[0]
            UserSetting.objects.create(lobby = lobby, nick = self.nick)
        except IntegrityError:
            logging.error(f'User {self.nick} exist name.')

    """
    Delete channel and lobby, if channel was last

    :param group_name: lobby name
    :param nick: channel ownder nick
    :return: is delete lobby 
    """
    @database_sync_to_async
    def delete_channel(self) -> bool:
        try:
            UserSetting.objects.filter(lobby__code = self.room_code, nick = self.nick).delete()
            count_channels = UserSetting.objects.filter(lobby__code = self.room_code).count()
            if count_channels == 0:
                LobbySetting.objects.get(code = self.room_code).delete()
                return True
            return False
        except (UserSetting.DoesNotExist, LobbySetting.DoesNotExist):
            return False

    @database_sync_to_async
    def get_random_board(self, difficulty):
        solution_board: QuerySet[SudokuCell] = SudokuBoard.objects.random(filter = {'difficulty__name': difficulty}, exclude = {'id__in': self.solution_id})
        if solution_board is None:
            solution_board: QuerySet[SudokuCell] = SudokuBoard.objects.random(filter = {'difficulty__name': difficulty})
            if solution_board is None:
                return None
            self.solution_id = [solution_board[0].board_id, ]
        else:
            self.solution_id.append(solution_board[0].board_id)
        
        clean_board = [[0 for _ in range(9)] for _ in range(9)]
        for cell in solution_board:
            row, col = cell.number // 9 , cell.number % 9
            if not cell.is_empty:
                clean_board[row][col] = cell.value

        return solution_board, clean_board