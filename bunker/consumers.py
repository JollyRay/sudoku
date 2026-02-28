import json
from typing import Any, Final, Optional
from urllib import response

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from bunker.models import Parameter
from common.redis import RedisClient


class BunkerConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    _REDIS_CLIENT: Final[RedisClient] = RedisClient()

    GROUP_NAME_TEMPLATE: Final[str] = 'bunker_{room_name}'
    ADMIN_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:admin'
    MEMBERS_KEY_TEMPLATE: Final[str] = 'bunker:{room_name}:members'
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

            self._is_admin_lobby = not self._REDIS_CLIENT.has(self.admin_key)
            if self._is_admin_lobby:
                await self._REDIS_CLIENT.set(self.admin_key, self.nick)
            await self._REDIS_CLIENT.push(self.members_key, self.nick)

            await self.accept()
        except Exception as e:
            print(f'Error during connection: {e}')
            await self.close()

    async def disconnect(self, code: int) -> None:
        try:
            await self._REDIS_CLIENT.rem(self.members_key, self.nick)
            counter = await self._REDIS_CLIENT.lenght(self.members_key)
            if counter == 0:
                await self._REDIS_CLIENT.delete(self.members_key)
                await self._REDIS_CLIENT.delete(self.admin_key)
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        except Exception as e:
            print(f'Error during disconnection: {e}')
    
    async def send_full_data(self, receiver: Optional[str] = None, **data: Any) -> None:
        await self.channel_layer.group_send(
            self.room_group_name, {'type': 'send_message_receiver', 'data': data, 'receiver': receiver}
        )
    
    async def send_message_receiver(self, data: dict[str, Any]) -> None:
        if data['receiver'] != self.nick and data['receiver'] is not None:
            return
        await self.send(text_data = json.dumps(data.get('data')))

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        text_data_json: dict[str, Any] = json.loads(text_data)
        await self.execute_handler(text_data_json)

    async def execute_handler(self, user_data: dict[str, Any]) -> None:
        raise NotImplementedError('execute_handler must be implemented in subclass')

    def get_member_key(self, member_nick: str) -> str:
        return f'{self.members_key}:{member_nick}'


class ClientEventService(BunkerConsumer):

    async def execute_handler(self, user_data: dict[str, Any]) -> None:
        kind: Optional[str] = user_data.get('kind')
        
        match kind:
            case 'init_board':
                await self.init_board(user_data)
            case 'get_board_data':
                await self.get_board_data(user_data)
            case 'set_field_value':
                await self.set_field_value(user_data)
            case 'swap_field_value':
                await self.swap_field_value(user_data)
            case 'steal_field_value':
                await self.steal_field_value(user_data)
            case 'open_field':
                await self.open_field(user_data)
            case _:
                print(f'Unknown kind: {kind}')

    async def init_board(self, user_data: dict[str, Any]) -> None:
        try:
            members: list[Any] = await self._REDIS_CLIENT.range(self.members_key)

            for member_nick in members:
                member_key: str = self.get_member_key(member_nick)
                await self._REDIS_CLIENT.delete(member_key)

                character_set: dict[str, str] = await database_sync_to_async(Parameter.objects.get_character_set)()
                character_data: list[dict[str, Any]] = [
                    {
                        'param_name': column_name,
                        'value': value,
                        'is_open': False
                    }
                    for column_name, value in character_set.items()
                ]
                await self._REDIS_CLIENT.set(member_key, json.dumps(character_data))
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
            print(f'Error initializing board: {e}')

    async def get_board_data(self, user_data: dict[str, Any]) -> None:
        try:
            members: list[Any] = await self._REDIS_CLIENT.range(self.members_key)
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            is_host: bool = admin == self.nick
            
            board_data: list[dict[str, Any]] = []
            self_data: list[dict[str, Any]] = []
            
            for member_nick in members:
                member_key: str = self.get_member_key(member_nick)
                member_data_json: str = await self._REDIS_CLIENT.get(member_key)
                
                if member_data_json is None:
                    continue
                
                member_data: list[dict[str, Any]] = json.loads(member_data_json)

                open_params: list[dict[str, str]] = [
                    {
                        'param_name': item['param_name'],
                        'value': item['value']
                    }
                    for item in member_data
                    if item.get('is_open', False)
                ]
                
                if open_params:
                    board_data.append({member_nick: open_params})

                if member_nick == self.nick:
                    self_data = [
                        {
                            'field_name': item['param_name'],
                            'value': item['value'],
                            'is_open': item.get('is_open', False)
                        }
                        for item in member_data
                    ]
            
            response: dict[str, Any] = {
                'kind': 'set_board_data',
                'members': members,
                'is_host': is_host,
                'board_data': board_data,
                'self_data': self_data
            }
            await self.send(text_data=json.dumps(response))
        except Exception as e:
            print(f'Error getting board data: {e}')

    async def set_field_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member: str = user_data['member']
            field_name: str = user_data['field_name']
            new_value: str = user_data['new_value']

            is_update = await self._set_member_field_value(member, field_name, new_value)
            if not is_update:
                return
            await self._send_data_to_members_with_scope(member=member, field_name=field_name)
        except Exception as e:
            print(f'Error setting field value: {e}')

    async def swap_field_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member1: str = user_data['member1']
            member2: str = user_data['member2']
            field_name: str = user_data['field_name']

            member1_field_value = await self._get_member_field_parameter(member1, field_name)
            member2_field_value = await self._get_member_field_parameter(member2, field_name)
            if member1_field_value is None or member2_field_value is None:
                return
            
            await self._set_member_field_value(
                member1,
                field_name,
                member2_field_value['value'],
                member2_field_value['is_open'],
            )
            await self._set_member_field_value(
                member2,
                field_name,
                member1_field_value['value'],
                member1_field_value['is_open'],
            )
            await self._send_data_to_members_with_scope(member=member1, field_name=field_name)
            await self._send_data_to_members_with_scope(member=member2, field_name=field_name)
        except Exception as e:
            print(f'Error swapping field value: {e}')

    async def steal_field_value(self, user_data: dict[str, str]) -> None:
        try:
            admin: str = await self._REDIS_CLIENT.get(self.admin_key)
            if admin != self.nick:
                return
            
            member1: str = user_data['member1']
            member2: str = user_data['member2']
            field_name: str = user_data['field_name']

            member1_field_value = await self._get_member_field_parameter(member1, field_name)
            member2_field_value = await self._get_member_field_parameter(member2, field_name)
            if member1_field_value is None or member2_field_value is None:
                return
            
            stolen_value = member1_field_value['value']
            old_value = member2_field_value['value']
            new_value = ', '.join(filter(None, [old_value, stolen_value]))

            await self._set_member_field_value(
                member1,
                field_name,
                '',
                member1_field_value['is_open'],
            )
            await self._set_member_field_value(
                member2,
                field_name,
                new_value,
                member2_field_value['is_open'],
            )
            await self._send_data_to_members_with_scope(member=member1, field_name=field_name)
            await self._send_data_to_members_with_scope(member=member2, field_name=field_name)
        except Exception as e:
            print(f'Error stealing field value: {e}')

    async def open_field(self, user_data: dict[str, str]) -> None:
        try:
            member = user_data['member']
            field_name= user_data['field_name']
            
            if member != self.nick:
                return

            member_field_value = await self._get_member_field_parameter(member, field_name)
            if member_field_value is None:
                return
            is_open = not member_field_value.get('is_open', True)
            await self._set_member_field_value(
                member,
                field_name,
                member_field_value['value'],
                is_open,
            )
            response = self._add_set_value_response(
                member,
                field_name,
                member_field_value['value'] if is_open else ''
            )
            await self.send_full_data(member=member, data=response)

        except Exception as e:
            print(f'Error opening field: {e}')

    def _add_set_value_response(
        self,
        member: str,
        field_name: str,
        new_value: str,
        response: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if response is None:
            response = {
                'kind': 'set_field_value',
                'updates': []
            }
        response['updates'].append({
            'member': member,
            'field_name': field_name,
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
    
    async def _get_member_field_parameter(self, member: str, field_name: str) -> Optional[dict[str, Any]]:
        member_data = await self._get_member_data(member)
        if not member_data:
            return None
        for parameter in member_data['fields']:
            if isinstance(parameter, dict) and parameter.get('param_name') == field_name:
                return parameter
        return None
    
    async def _set_member_field_value(self, member: str, field_name: str, new_value: str, is_open: Optional[bool] = None) -> bool:
        member_data = await self._get_member_data(member)
        if not member_data:
            return False
        for parameter in member_data['fields']:
            if parameter['param_name'] == field_name:
                parameter['value'] = new_value
                if is_open is not None:
                    parameter['is_open'] = is_open
                await self._REDIS_CLIENT.set(self.get_member_key(member), json.dumps(member_data))
                return True
        return False
    
    async def _send_data_to_members_with_scope(self, member: str, field_name: str) -> None:
        parameter_data = await self._get_member_field_parameter(member, field_name)
        if parameter_data is None:
            return
        data = self._add_set_value_response(member, field_name, parameter_data.get('value', ''))
        if parameter_data.get('is_open', False):
            receiver = None
        else:
            receiver = member

        await self.send_full_data(
            receiver=receiver,
            data=data
        )
