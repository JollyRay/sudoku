import json
from typing import Any
from urllib.parse import quote

from common.redis import RedisClient


class SudokuVibeStorage:
    EXPIRY_SECONDS = 7200

    def __init__(self, redis: RedisClient | None = None) -> None:
        self.redis = redis or RedisClient()

    @staticmethod
    def _lobby_prefix(lobby: str) -> str:
        return f"sudoku-vibe:{quote(lobby, safe='')}"

    @classmethod
    def _contexts_key(cls, lobby: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:contexts"

    @classmethod
    def _board_names_key(cls, lobby: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:board-names"

    @classmethod
    def _board_key(cls, lobby: str, board_name: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:board:{quote(board_name, safe='')}"

    @classmethod
    def _fixed_cells_key(cls, lobby: str, board_name: str) -> str:
        return f"{cls._board_key(lobby, board_name)}:fixed-cells"

    async def save_context(
        self,
        lobby: str,
        username: str,
        context: dict[str, Any],
    ) -> None:
        key = self._contexts_key(lobby)
        await self.redis.hset(key, username, json.dumps(context))
        await self.redis.expire(key, self.EXPIRY_SECONDS)

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

    async def replace_board(
        self,
        lobby: str,
        board_name: str,
        values: dict[str, int | str],
        fixed_cells: set[int],
    ) -> None:
        board_key = self._board_key(lobby, board_name)
        fixed_cells_key = self._fixed_cells_key(lobby, board_name)
        board_names_key = self._board_names_key(lobby)
        serialized_values = {
            cell_index: json.dumps(value)
            for cell_index, value in values.items()
        }

        await self.redis.delete(board_key)
        await self.redis.delete(fixed_cells_key)
        if serialized_values:
            await self.redis.hmset(board_key, serialized_values)
        if fixed_cells:
            await self.redis.hmset(
                fixed_cells_key,
                {str(cell_index): "1" for cell_index in fixed_cells},
            )
        await self.redis.sadd(board_names_key, board_name)
        await self.redis.expire(board_key, self.EXPIRY_SECONDS)
        await self.redis.expire(fixed_cells_key, self.EXPIRY_SECONDS)
        await self.redis.expire(board_names_key, self.EXPIRY_SECONDS)

    async def set_cell(
        self,
        lobby: str,
        board_name: str,
        cell_index: int,
        value: int | str,
    ) -> None:
        board_key = self._board_key(lobby, board_name)
        fixed_cells_key = self._fixed_cells_key(lobby, board_name)
        board_names_key = self._board_names_key(lobby)

        await self.redis.hset(board_key, str(cell_index), json.dumps(value))
        await self.redis.sadd(board_names_key, board_name)
        await self.redis.expire(board_key, self.EXPIRY_SECONDS)
        await self.redis.expire(fixed_cells_key, self.EXPIRY_SECONDS)
        await self.redis.expire(board_names_key, self.EXPIRY_SECONDS)

    async def has_board(self, lobby: str, board_name: str) -> bool:
        return await self.redis.sismember(
            self._board_names_key(lobby),
            board_name,
        )

    async def is_fixed_cell(
        self,
        lobby: str,
        board_name: str,
        cell_index: int,
    ) -> bool:
        return await self.redis.hexist(
            self._fixed_cells_key(lobby, board_name),
            str(cell_index),
        )

    async def get_boards(
        self,
        lobby: str,
    ) -> dict[str, dict[str, int | str]]:
        board_names = await self.redis.smembers(self._board_names_key(lobby))
        boards: dict[str, dict[str, int | str]] = {}

        for board_name in board_names:
            stored_values = await self.redis.hgetall(
                self._board_key(lobby, board_name),
            )
            boards[board_name] = {
                cell_index: json.loads(value)
                for cell_index, value in stored_values.items()
            }

        return boards

    async def get_lobby_state(
        self,
        lobby: str,
        username: str,
    ) -> tuple[dict[str, Any] | None, dict[str, dict[str, int | str]]]:
        context = await self.get_context(lobby, username)
        boards = await self.get_boards(lobby)
        return context, boards
