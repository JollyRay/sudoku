import json
from typing import Any, TypedDict
from urllib.parse import quote, unquote

from common.redis import RedisClient


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


class StoredBoard(TypedDict):
    public: PublicBoard
    solution: dict[str, int]


def empty_board(name: str) -> PublicBoard:
    return {
        "name": name, "generationId": None, "revision": 0, "size": 9,
        "difficulty": None, "values": {}, "fixedCells": [], "bonuses": {},
        "wrongCells": [], "startedAt": None, "finishedAt": None,
        "completed": False, "requiresGeneration": False,
    }


class SudokuVibeStorage:
    PRESENCE_EXPIRY_SECONDS = 90

    def __init__(self, redis: RedisClient | None = None) -> None:
        self.redis = redis or RedisClient()

    @staticmethod
    def _lobby_prefix(lobby: str) -> str:
        return f"sudoku-vibe:{quote(lobby, safe='')}"

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
        return await self.redis.acquire_room_presence(
            self._lobby_prefix(lobby),
            self._presence_key(lobby, username),
            connection_id,
            self.PRESENCE_EXPIRY_SECONDS,
        )

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
        return await self.redis.release_room_presence(
            self._lobby_prefix(lobby),
            self._presence_key(lobby, username),
            connection_id,
        )

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

    async def get_board_state(self, lobby: str, name: str) -> StoredBoard | None:
        key = self._board_key(lobby, name)
        values, fixed, metadata, solution = await self.redis.read_hashes(
            [key, self._fixed_cells_key(lobby, name), f"{key}:metadata", f"{key}:solution"]
        )
        if not values and not metadata:
            return None
        board = empty_board(name)
        if metadata.get("state"):
            board.update(json.loads(metadata["state"]))
        else:
            board["requiresGeneration"] = True
        board["values"] = {index: json.loads(value) for index, value in values.items()}
        board["fixedCells"] = sorted(int(index) for index in fixed)
        return {"public": board, "solution": {index: int(value) for index, value in solution.items()}}

    async def save_board_state(
        self, lobby: str, name: str, board: StoredBoard,
        expected: tuple[str | None, int] | None, connection_id: str,
    ) -> str:
        key = self._board_key(lobby, name)
        public = board["public"]
        metadata = {k: v for k, v in public.items() if k not in {"values", "fixedCells"}}
        return await self.redis.compare_and_replace_hashes(
            self._presence_key(lobby, name), connection_id, f"{key}:metadata",
            {"generationId": str(expected[0]), "revision": str(expected[1])} if expected else None,
            {
                key: {i: json.dumps(v) for i, v in public["values"].items()},
                self._fixed_cells_key(lobby, name): {str(i): "1" for i in public["fixedCells"]},
                f"{key}:metadata": {"state": json.dumps(metadata),
                                    "generationId": str(public["generationId"]), "revision": str(public["revision"])},
                f"{key}:solution": {i: str(v) for i, v in board["solution"].items()},
            },
        )
