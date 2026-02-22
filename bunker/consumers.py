from copy import copy
import json
from typing import Any, Final

from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from common.redis import RedisClient


class _BunkerRedisKey:
    REDIS_GROUP_PREFIX: Final[str] = 'bunker:group:{group_name}:{key}'
    GROUP_MEMBERS_KEY: Final[str] = 'members'
    GROUP_ADMIN_KEY: Final[str] = 'admin'
    GROUP_BOARD_KEY: Final[str] = 'board_data' # {username: [{param_name: str, value: str, is_open: bool}], ...}
    room_group_name: str = ''

    @property
    def admin_key(self) -> str:
        return self.REDIS_GROUP_PREFIX.format(
            group_name=self.room_group_name,
            key=self.GROUP_ADMIN_KEY,
        )
    
    @property
    def members_key(self) -> str:
        return self.REDIS_GROUP_PREFIX.format(
            group_name=self.room_group_name,
            key=self.GROUP_MEMBERS_KEY,
        )
    
    @property
    def board_key(self) -> str:
        return self.REDIS_GROUP_PREFIX.format(
            group_name=self.room_group_name,
            key=self.GROUP_BOARD_KEY,
        )


class BunkerConsumer(AsyncWebsocketConsumer, _BunkerRedisKey):  # type: ignore[misc]
    
    async def connect(self) -> None:
        self.room_name = self.scope.get('url_route', {}).get('kwargs', {}).get('room_name')
        self.nick: str = self.scope.get('cookies', {}).get('nick', '')
        if not self.room_name or not self.nick:
            return
        self.room_group_name = f'bunker_{self.room_name}'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        self._redis: RedisClient = RedisClient()
 
        self._is_admin_lobby = not self._redis.has(self.admin_key)
        if self._is_admin_lobby:
            await self._redis.set(self.admin_key, self.nick)
        
        counter = await self._redis.push(self.members_key, self.nick)
        self.is_host = counter == 1

    async def disconnect(self, code: int) -> None:
        await self._redis.rem(self.members_key, self.nick)
        counter = await self._redis.lenght(self.members_key)
        if counter == 0:
            await self._redis.delete(self.members_key)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        answer: Any
        text_data_json: dict[str, Any] = json.loads(text_data)
        match text_data_json.get('kind'):
            case 'board_init':
                answer = await self.get_first_data()
            case 'generate_board':
                answer = 'empty'
            case 'set_field_value':
                answer = 'empty'
            case 'swap_field_value':
                answer = 'empty'
            case 'steal_field_value':
                answer = 'empty'
            case _:
                return

        await self.channel_layer.group_send(
            self.room_group_name, {'type': 'board.send', 'data': answer}
        )

    async def board_send(self, event: dict[str, Any]) -> None:
        message = event['data']
        await self.send(text_data=json.dumps(message))

    async def get_first_data(self) -> dict[str, Any]:

        size = await self._redis.lenght(self.members_key)
        board_data: dict[str, Any] = await self._redis.get(self.board_key, {})
        board_data_array: list[dict[str, Any]] = []
        self_data: list[dict[str, str]] = []

        for pramas in board_data.get(self.nick, []):
            self_data.append(copy(pramas))
        
        for username, pramas in board_data.items():
            user_info: list[dict[str, str]] = []
            for param in pramas:
                if param['is_open']:
                    param_copy = copy(param)
                    del param_copy['is_open']
                    user_info.append(param_copy)
            if user_info:
                board_data_array.append({
                    'user_name': username,
                    'data': user_info
                })

        answer = {
            'kind': 'first_data',
            'size': size,
            'is_host': self.is_host,
            'board_data': board_data_array,
            'self_data': self_data,
        }
        return answer
