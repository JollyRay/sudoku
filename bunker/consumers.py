import json
import logging
from typing import Any, Final, Optional
from random import shuffle

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from bunker.models import Parameter
from common.redis import RedisClient


logger = logging.getLogger(__name__)


class BunkerConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    _REDIS_CLIENT: Final[RedisClient] = RedisClient()

    GROUP_NAME_TEMPLATE: Final[str] = 'bunker_{room_name}'
    ADMIN_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:admin'
    MEMBERS_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:members'
    MEMBERS_BAN_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:ban_members'
    MEMBERS_OPEN_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:param_open'

    async def connect(self) -> None:
        try: 
            self.room_name: str = self.scope.get('url_route', {}).get('kwargs', {})['room_name']
            self.nick: str = self.scope.get('cookies', {})['nick']
            self.room_group_name = self.GROUP_NAME_TEMPLATE.format(room_name=self.room_name)
            self.admin_key = self.ADMIN_KEY_TEMPLATE.format(room_name=self.room_name)
            self.members_key = self.MEMBERS_KEY_TEMPLATE.format(room_name=self.room_name)
            self.members_open_key = self.MEMBERS_OPEN_KEY_TEMPLATE.format(room_name=self.room_name)

            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

            admin_nick = await self._REDIS_CLIENT.get(self.admin_key)
            self._is_admin_lobby = admin_nick is None or self.nick == admin_nick
            if admin_nick is None:
                await self._REDIS_CLIENT.set(self.admin_key, self.nick)
            await self._REDIS_CLIENT.push(self.members_key, self.nick)

            await self.accept()
        except Exception as e:
            logger.error(f'Error during connection: {e}')
            await self.close()

    async def disconnect(self, code: int) -> None:
        try:
            await self._REDIS_CLIENT.rem(self.members_key, self.nick)
            counter = await self._REDIS_CLIENT.length(self.members_key)
            if counter <= 0:
                await self._REDIS_CLIENT.delete(self.members_key)
                await self._REDIS_CLIENT.delete(self.admin_key)
                await self._REDIS_CLIENT.delete(self.ban_member_key)
                await self._REDIS_CLIENT.delete_pattern(pattern=f'{self.members_key}:*')
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        except Exception as e:
            logger.error(f'Error during disconnection: {e}')
    
    async def send_full_data(
        self,
        receiver: Optional[str] = None,
        not_receiver: Optional[str] = None,
        data: dict[str, Any] = {},
    ) -> None:
        await self.channel_layer.group_send(
            self.room_group_name, {
                'type': 'send_message_receiver',
                'data': data,
                'receiver': receiver,
                'not_receiver': not_receiver
            }
        )
    
    async def send_message_receiver(self, data: dict[str, Any]) -> None:
        if data['receiver'] == self.nick or data['receiver'] is None and data['not_receiver'] != self.nick:
            await self.send(text_data = json.dumps(data['data']))

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        text_data_json: dict[str, Any] = json.loads(text_data)
        await self.execute_handler(text_data_json)

    async def execute_handler(self, user_data: dict[str, Any]) -> None:
        raise NotImplementedError('execute_handler must be implemented in subclass')

    def get_member_key(self, member_nick: str) -> str:
        return f'{self.members_key}:{member_nick}'
    
    @property
    def ban_member_key(self) -> str:
        return self.MEMBERS_BAN_KEY_TEMPLATE.format(room_name=self.room_name)


class ClientEventService(BunkerConsumer):

    async def execute_handler(self, user_data: dict[str, Any]) -> None:
        kind: Optional[str] = user_data.get('kind')
        
        match kind:
            case 'init_board':
                await self.init_board(user_data)
            case 'get_board_data':
                await self.get_board_data(user_data)
            case 'set_param_value':
                await self.set_param_value(user_data)
            case 'swap_param_value':
                await self.swap_param_value(user_data)
            case 'steal_param_value':
                await self.steal_param_value(user_data)
            case 'open_param':
                await self.open_param(user_data)
            case 'toggle_status':
                await self.toggle_status(user_data)
            case _:
                logger.warning(f'Unknown kind: {kind}')

    async def init_board(self, user_data: dict[str, Any]) -> None:
        try:
            members: list[Any] = await self._REDIS_CLIENT.range(self.members_key)
            shuffle(members)
            await self._REDIS_CLIENT.delete(self.members_key)
            for member_nick in members:
                await self._REDIS_CLIENT.push(self.members_key, member_nick)
            await self._REDIS_CLIENT.delete_pattern(pattern=f'{self.members_key}:*')

            for member_nick in members:
                member_key: str = self.get_member_key(member_nick)

                character_set: dict[str, str] = await database_sync_to_async(Parameter.objects.get_character_set)()
                character_data: list[dict[str, Any]] = [
                    {
                        'param_name': column_name,
                        'value': value,
                        'is_open': False
                    }
                    for column_name, value in character_set.items()
                ]
                await self._REDIS_CLIENT.set(member_key, json.dumps({"params": character_data}))
                await self.send_full_data(
                    receiver=member_nick,
                    data={
                        'kind': 'board_init',
                        'members': members,
                        'self_data': character_data,
                        'story': {}
                    }
                )
        except Exception as e:
            logger.error(f'Error initializing board: {e}')

    async def get_board_data(self, user_data: dict[str, Any]) -> None:
        try:
            members: list[Any] = await self._REDIS_CLIENT.range(self.members_key)
            exist_members: list[str] = []
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            is_host: bool = admin == self.nick
            baned_members: list[str] = list(await self._REDIS_CLIENT.smembers(self.ban_member_key))
            
            board_data: dict[str, Any] = {}
            self_data: list[dict[str, Any]] = []
            
            for member_nick in members:
                member_key: str = self.get_member_key(member_nick)
                member_data_json: str = await self._REDIS_CLIENT.get(member_key)
                
                if member_data_json is None:
                    continue
                
                exist_members.append(member_nick)
                member_data: dict[str, list[dict[str, Any]]] = json.loads(member_data_json)

                open_params: list[dict[str, str]] = [
                    {
                        'param_name': item['param_name'],
                        'value': item['value']
                    }
                    for item in member_data['params']
                    if item.get('is_open', False)
                ]
                
                if open_params:
                    board_data[member_nick] = open_params

                if member_nick == self.nick:
                    self_data = [
                        {
                            'param_name': item['param_name'],
                            'value': item['value'],
                            'is_open': item.get('is_open', False)
                        }
                        for item in member_data['params']
                    ]
            
            response: dict[str, Any] = {
                'kind': 'set_board_data',
                'members': exist_members,
                'baned_members': baned_members,
                'is_host': is_host,
                'board_data': board_data,
                'self_data': self_data
            }
            await self.send(text_data=json.dumps(response))
        except Exception as e:
            logger.error(f'Error getting board data: {e}', exc_info=True)

    async def set_param_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member: str = user_data['member']
            param_name: str = user_data['param_name']
            new_value: str = user_data['new_value']

            is_update = await self._set_member_param_value(member, param_name, new_value)
            if not is_update:
                return
            await self._send_data_to_members_with_scope(member=member, param_name=param_name)
        except Exception as e:
            logger.error(f'Error setting param value: {e}')

    async def swap_param_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member1: str = user_data['member1']
            member2: str = user_data['member2']
            param_name: str = user_data['param_name']

            member1_param_value = await self._get_member_param_parameter(member1, param_name)
            member2_param_value = await self._get_member_param_parameter(member2, param_name)
            if member1_param_value is None or member2_param_value is None:
                return
            
            await self._set_member_param_value(
                member1,
                param_name,
                member2_param_value['value'],
                member2_param_value['is_open'],
            )
            await self._set_member_param_value(
                member2,
                param_name,
                member1_param_value['value'],
                member1_param_value['is_open'],
            )
            await self._send_data_to_members_with_scope(member=member1, param_name=param_name)
            await self._send_data_to_members_with_scope(member=member2, param_name=param_name)
        except Exception as e:
            logger.error(f'Error swapping param value: {e}')

    async def steal_param_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member1: str = user_data['member_from']
            member2: str = user_data['member_to']
            param_name: str = user_data['param_name']

            member1_param_value = await self._get_member_param_parameter(member1, param_name)
            member2_param_value = await self._get_member_param_parameter(member2, param_name)
            if member1_param_value is None or member2_param_value is None:
                return
            
            stolen_value = member1_param_value['value']
            old_value = member2_param_value['value']
            new_value = ', '.join(filter(None, [old_value, stolen_value]))

            await self._set_member_param_value(
                member1,
                param_name,
                '',
                member1_param_value['is_open'],
            )
            await self._set_member_param_value(
                member2,
                param_name,
                new_value,
                member2_param_value['is_open'],
            )
            await self._send_data_to_members_with_scope(member=member1, param_name=param_name)
            await self._send_data_to_members_with_scope(member=member2, param_name=param_name)
        except Exception as e:
            logger.error(f'Error stealing param value: {e}')

    async def open_param(self, user_data: dict[str, str]) -> None:
        try:
            param_name = user_data['param_name']

            member_param_value = await self._get_member_param_parameter(self.nick, param_name)
            if member_param_value is None:
                return
            is_open = not member_param_value.get('is_open', True)
            await self._set_member_param_value(
                self.nick,
                param_name,
                member_param_value['value'],
                is_open,
            )
            response = self._add_set_value_response(
                self.nick,
                param_name,
                member_param_value['value'] if is_open else ''
            )

            await self.send_full_data(not_receiver=self.nick, data=response)
            self_open_response = {'kind': 'open_param', 'param_name': param_name, 'is_open': is_open}
            await self.send_full_data(receiver=self.nick, data=self_open_response)

        except Exception as e:
            logger.error(f'Error opening param: {e}')

    async def toggle_status(self, user_data: dict[str, str]) -> None:
        admin: str = await self._REDIS_CLIENT.get(self.admin_key)
        if admin != self.nick:
            return
        try:
            member: str = user_data['member']
            is_banned: bool = await self._REDIS_CLIENT.sismember(self.ban_member_key, member)
            if is_banned:
                await self._REDIS_CLIENT.srem(self.ban_member_key, member)
            else:
                await self._REDIS_CLIENT.sadd(self.ban_member_key, member)
            await self.send_full_data(data={'kind': 'toggle_status', 'member': member, 'is_banned': not is_banned})
        except Exception as e:
            logger.error(f'Error checking member status: {e}')

    def _add_set_value_response(
        self,
        member: str,
        param_name: str,
        new_value: str,
        response: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if response is None:
            response = {
                'kind': 'set_param_value',
                'updates': []
            }
        response['updates'].append({
            'member': member,
            'param_name': param_name,
            'new_value': new_value
        })
        return response
    
    async def _get_member_data(self, member: str) -> Optional[dict[str, Any]]:
        member_key: str = self.get_member_key(member)
        member_data_json = await self._REDIS_CLIENT.get(member_key)
        if not isinstance(member_data_json, str):
            return None
        data = json.loads(member_data_json)
        if isinstance(data, dict):
            return data
        return None
    
    async def _get_member_param_parameter(self, member: str, param_name: str) -> Optional[dict[str, Any]]:
        member_data = await self._get_member_data(member)
        if not member_data:
            return None
        for parameter in member_data['params']:
            if isinstance(parameter, dict) and parameter.get('param_name') == param_name:
                return parameter
        return None
    
    async def _set_member_param_value(
        self,
        member: str,
        param_name: str,
        new_value: str,
        is_open: Optional[bool] = None,
    ) -> bool:
        member_data = await self._get_member_data(member)
        if not member_data:
            return False
        for parameter in member_data['params']:
            if parameter['param_name'] == param_name:
                parameter['value'] = new_value
                if is_open is not None:
                    parameter['is_open'] = is_open
                await self._REDIS_CLIENT.set(self.get_member_key(member), json.dumps(member_data))
                return True
        return False
    
    async def _send_data_to_members_with_scope(self, member: str, param_name: str) -> None:
        parameter_data = await self._get_member_param_parameter(member, param_name)
        if parameter_data is None:
            return
        data = self._add_set_value_response(member, param_name, parameter_data.get('value', ''))
        if parameter_data.get('is_open', False):
            receiver = None
        else:
            receiver = member

        await self.send_full_data(
            receiver=receiver,
            data=data
        )
