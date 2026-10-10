import json
from typing import Any
from urllib.parse import quote, unquote

from common.redis import RedisClient


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
    def _board_names_key(cls, lobby: str) -> str:
        return f"{cls._lobby_prefix(lobby)}:board-names"

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
        return await self.redis.set_if_absent(
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
        return await self.redis.delete_if_value(
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
        connection_id: str | None = None,
    ) -> bool:
        key = self._contexts_key(lobby)
        if connection_id is not None:
            return await self.redis.hset_if_value(
                self._presence_key(lobby, username),
                connection_id,
                key,
                username,
                json.dumps(context),
            )

        await self.redis.hset(key, username, json.dumps(context))
        return True

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
        connection_id: str | None = None,
    ) -> bool:
        board_key = self._board_key(lobby, board_name)
        fixed_cells_key = self._fixed_cells_key(lobby, board_name)
        board_names_key = self._board_names_key(lobby)
        serialized_values = {
            cell_index: json.dumps(value)
            for cell_index, value in values.items()
        }

        hashes = {
            board_key: serialized_values,
            fixed_cells_key: {
                str(cell_index): "1" for cell_index in fixed_cells
            },
        }
        set_members = {board_names_key: board_name}
        if connection_id is not None:
            return await self.redis.atomic_replace_hashes_if_value(
                self._presence_key(lobby, board_name),
                connection_id,
                hashes,
                set_members,
            )

        await self.redis.atomic_replace_hashes(hashes, set_members)
        return True

    async def set_cell(
        self,
        lobby: str,
        board_name: str,
        cell_index: int,
        value: int | str,
        connection_id: str | None = None,
    ) -> int:
        board_key = self._board_key(lobby, board_name)
        return await self.redis.hset_if_mutable(
            (
                self._presence_key(lobby, board_name)
                if connection_id is not None
                else ""
            ),
            connection_id or "",
            board_key,
            str(cell_index),
            json.dumps(value),
            self._fixed_cells_key(lobby, board_name),
        )

    async def has_board(self, lobby: str, board_name: str) -> bool:
        return (
            await self.redis.sismember(
                self._board_names_key(lobby),
                board_name,
            )
            and await self.redis.exists(self._board_key(lobby, board_name))
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

    async def get_fixed_cells(
        self,
        lobby: str,
        board_name: str,
    ) -> set[int]:
        return {
            int(cell_index)
            for cell_index in await self.redis.hkeys(
                self._fixed_cells_key(lobby, board_name)
            )
        }

    async def get_lobby_state(
        self,
        lobby: str,
        username: str,
    ) -> tuple[dict[str, Any] | None, dict[str, dict[str, int | str]]]:
        context = await self.get_context(lobby, username)
        boards = await self.get_boards(lobby)
        return context, boards
