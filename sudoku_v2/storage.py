import json
from functools import lru_cache
from time import time
from uuid import uuid4
from typing import Any, TypedDict
from urllib.parse import quote, unquote, urlparse

from django.conf import settings
from common.redis import RedisClient, RedisConfig, CommitGuard, ExpiringValue
from .constants import BONUS_DEFINITIONS


@lru_cache(maxsize=1)
def configured_redis(url: str) -> RedisClient:
    parsed = urlparse(url)
    # Do not reuse the legacy global singleton in the isolated preview.
    client = object.__new__(RedisClient)
    client._config = RedisConfig(host=parsed.hostname, port=parsed.port or 6379,
                                 db=int(parsed.path.lstrip('/')), password=parsed.password)
    client._redis_client = client._create_connection()
    return client


BoardValue = int | str


class PublicBoard(TypedDict):
    name: str
    generationId: str | None
    revision: int
    size: int
    difficulty: str | None
    values: dict[str, BoardValue]
    fixedCells: list[int]
    bonuses: dict[str, str]
    wrongCells: list[int]
    startedAt: int | None
    finishedAt: int | None
    completed: bool
    requiresGeneration: bool
    rowOrder: list[int]
    columnOrder: list[int]
    consumedBonusCells: list[int]
    activeEffects: list[dict[str, Any]]


class StoredBoard(TypedDict):
    public: PublicBoard
    solution: dict[str, int]


def empty_board(name: str, size: int = 9) -> PublicBoard:
    return {
        "name": name, "generationId": None, "revision": 0, "size": size,
        "difficulty": None, "values": {}, "fixedCells": [], "bonuses": {},
        "wrongCells": [], "startedAt": None, "finishedAt": None,
        "completed": False, "requiresGeneration": False,
        "rowOrder": list(range(size)), "columnOrder": list(range(size)),
        "consumedBonusCells": [], "activeEffects": [],
    }


class SudokuV2Storage:
    PRESENCE_EXPIRY_SECONDS = 90

    def __init__(self, redis: RedisClient | None = None) -> None:
        url = getattr(settings, 'SUDOKU_V2_REDIS_URL', '')
        self.redis = redis or (configured_redis(url) if url else RedisClient())

    @staticmethod
    def _lobby_prefix(lobby: str) -> str:
        return f"{getattr(settings, 'SUDOKU_V2_PREFIX', 'sudoku-v2')}:{quote(lobby, safe='')}"

    @classmethod
    def _contexts_key(cls, lobby: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:contexts"

    @classmethod
    def _board_key(cls, lobby: str, board_name: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:board:{quote(board_name, safe='')}"

    @classmethod
    def _fixed_cells_key(cls, lobby: str, board_name: str) -> str:
        return f"{cls._board_key(lobby, board_name)}:fixed-cells"

    @classmethod
    def _presence_key(cls, lobby: str, username: str) -> str:
        return f"{cls._presence_prefix(lobby)}{quote(username, safe='')}"

    @classmethod
    def _presence_prefix(cls, lobby: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:presence:"

    async def acquire_presence(
        self,
        lobby: str,
        username: str,
        connection_id: str,
    ) -> bool:
        previous_epoch = await self.get_room_epoch(lobby)
        acquired = await self.redis.acquire_room_presence(
            self._lobby_prefix(lobby),
            self._presence_key(lobby, username),
            connection_id,
            self.PRESENCE_EXPIRY_SECONDS,
            uuid4().hex,
        )
        if acquired and previous_epoch and await self.get_room_epoch(lobby) != previous_epoch:
            from .twitch.registry import TwitchRegistry
            await TwitchRegistry(self).cleanup_lobby(lobby, previous_epoch)
        return acquired

    async def get_room_epoch(self, lobby: str) -> str | None:
        return await self.redis.get(f'{self._lobby_prefix(lobby)}:epoch')

    async def get_presence_token(self, lobby: str, name: str) -> str | None:
        return await self.redis.get(self._presence_key(lobby, name))

    async def renew_presence(
        self,
        lobby: str,
        username: str,
        connection_id: str,
    ) -> bool:
        return await self.redis.expire_if_value(
            self._presence_key(lobby, username),
            connection_id,
            self.PRESENCE_EXPIRY_SECONDS,
        )

    async def release_presence(
        self,
        lobby: str,
        username: str,
        connection_id: str,
    ) -> bool:
        previous_epoch = await self.get_room_epoch(lobby)
        released = await self.redis.release_room_presence(
            self._lobby_prefix(lobby),
            self._presence_key(lobby, username),
            connection_id,
        )
        if previous_epoch and await self.get_room_epoch(lobby) != previous_epoch:
            from .twitch.registry import TwitchRegistry
            await TwitchRegistry(self).cleanup_lobby(lobby, previous_epoch)
        return released

    def is_username_active(self, lobby: str, username: str) -> bool:
        return self.redis.exists_sync(self._presence_key(lobby, username))

    async def get_active_usernames(self, lobby: str) -> set[str]:
        prefix = self._presence_prefix(lobby)
        keys = await self.redis.keys(f"{prefix}*")
        return {unquote(key.removeprefix(prefix)) for key in keys}

    async def save_context(
        self,
        lobby: str,
        username: str,
        context: dict[str, Any],
        connection_id: str,
    ) -> bool:
        key = self._contexts_key(lobby)
        return await self.redis.hset_if_value(
            self._presence_key(lobby, username), connection_id,
            key, username, json.dumps(context),
        )

    async def get_context(
        self,
        lobby: str,
        username: str,
    ) -> dict[str, Any] | None:
        raw_context = await self.redis.hget(
            self._contexts_key(lobby),
            username,
        )
        if raw_context is None:
            return None
        context = json.loads(raw_context)
        if not isinstance(context, dict):
            return None
        return context

    async def save_context_for_board(self, lobby: str, name: str, context: dict[str, Any],
                                     expected: tuple[str | None, int] | None, connection_id: str) -> str:
        return await self.redis.compare_and_replace_hashes(
            self._presence_key(lobby, name), connection_id, f"{self._board_key(lobby, name)}:metadata",
            {"generationId": str(expected[0]), "revision": str(expected[1])} if expected else None,
            {}, hash_updates={self._contexts_key(lobby): {name: json.dumps(context)}},
        )

    async def get_board_state(self, lobby: str, name: str) -> StoredBoard | None:
        key = self._board_key(lobby, name)
        values, fixed, metadata, solution = await self.redis.read_hashes(
            [key, self._fixed_cells_key(lobby, name), f"{key}:metadata", f"{key}:solution"]
        )
        if not values and not metadata:
            return None
        board = empty_board(name)
        if metadata.get("state"):
            state = json.loads(metadata['state'])
            board = {**empty_board(name, state.get('size', 9)), **state}
        else:
            board["requiresGeneration"] = True
        board["values"] = {index: json.loads(value) for index, value in values.items()}
        board["fixedCells"] = sorted(int(index) for index in fixed)
        supported_bonuses = {code for code, _, _ in BONUS_DEFINITIONS}
        board['bonuses'] = {index: kind for index, kind in board['bonuses'].items()
                            if kind in supported_bonuses}
        board['activeEffects'] = [effect for effect in board['activeEffects']
                                  if effect['kind'] in supported_bonuses
                                  and effect['expiresAt'] > int(time()*1000)]
        return {"public": board, "solution": {index: int(value) for index, value in solution.items()}}

    def _state_hashes(self, lobby: str, name: str, board: StoredBoard) -> dict[str, dict]:
        key, public = self._board_key(lobby, name), board['public']
        metadata = {k: v for k, v in public.items() if k not in {'values', 'fixedCells'}}
        return {
            key: {i: json.dumps(v) for i, v in public['values'].items()},
            self._fixed_cells_key(lobby, name): {str(i): '1' for i in public['fixedCells']},
            f'{key}:metadata': {'state': json.dumps(metadata), 'generationId': str(public['generationId']), 'revision': str(public['revision'])},
            f'{key}:solution': {i: str(v) for i, v in board['solution'].items()},
        }

    async def commit_boards(self, lobby: str, boards: dict[str, StoredBoard],
                            expected: dict[str, tuple[str, int, str]], *,
                            guards=(), strings: dict[str, ExpiringValue] | None = None,
                            hash_updates: dict[str, dict] | None = None) -> str:
        checks, hashes = list(guards), {}
        for name, board in boards.items():
            generation, revision, lease = expected[name]
            checks.extend([
                CommitGuard(self._presence_key(lobby, name), 'string', lease),
                CommitGuard(f'{self._board_key(lobby, name)}:metadata', 'hash',
                            {'generationId': str(generation), 'revision': str(revision)}),
            ])
            hashes.update(self._state_hashes(lobby, name, board))
        return await self.redis.compare_and_write_batch(checks, hashes, strings or {}, hash_updates=hash_updates)

    async def save_board_state(
        self, lobby: str, name: str, board: StoredBoard,
        expected: tuple[str | None, int] | None, connection_id: str,
        *, context: dict[str, Any] | None = None, expected_context: dict[str, Any] | None = None,
    ) -> str:
        key = self._board_key(lobby, name)
        return await self.redis.compare_and_replace_hashes(
            self._presence_key(lobby, name), connection_id, f"{key}:metadata",
            {"generationId": str(expected[0]), "revision": str(expected[1])} if expected else None,
            self._state_hashes(lobby, name, board),
            hash_updates={self._contexts_key(lobby): {name: json.dumps(context)}} if context is not None else None,
            expected_fields={self._contexts_key(lobby): {name: json.dumps(expected_context) if expected_context is not None else None}}
            if context is not None else None,
        )
