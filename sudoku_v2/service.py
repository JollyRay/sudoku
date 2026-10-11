from copy import deepcopy
from random import choice, sample
from time import time
from typing import Any, cast
from uuid import uuid4

from django.templatetags.static import static
from game.models import Difficulty, SudokuBoard, SudokuCell

from .constants import (
    BOARD_CELL_COUNT, BOARD_SIDE, BONUS_DEFINITIONS, DEFAULT_ALLOWED_VALUES,
    SUPPORTED_SIZES, SYMBOL_PRESET_DEFINITIONS,
)
from .storage import BoardValue, PublicBoard, StoredBoard, SudokuV2Storage, empty_board
from .user_context import normalize_context, valid_board_value


class SudokuV2Error(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SudokuV2Service:
    def __init__(self, lobby: str, username: str, storage: SudokuV2Storage,
                 connection_id: str) -> None:
        self.lobby = lobby
        self.username = username
        self.storage = storage
        self.connection_id = connection_id

    @staticmethod
    def now_ms() -> int:
        return int(time() * 1000)

    @staticmethod
    async def get_catalog() -> dict[str, Any]:
        labels = {"easy": "Лёгкая", "medium": "Средняя", "hard": "Сложная"}
        difficulties = [
            {"value": name, "label": labels.get(name, name)}
            async for name in Difficulty.objects.order_by("top_limit").values_list("name", flat=True)
        ]
        return {
            "difficulties": difficulties, "sizes": list(SUPPORTED_SIZES),
            "bonuses": [{"id": code, "label": label, "symbol": symbol}
                        for code, label, symbol in BONUS_DEFINITIONS],
            "symbolPresets": [{"id": code, "label": label, "imageUrl": static(path) if path else None}
                              for code, label, path in SYMBOL_PRESET_DEFINITIONS],
        }

    async def get_board_data(self, data: dict[str, Any]) -> dict[str, Any]:
        catalog = await self.get_catalog()
        context = await self.storage.get_context(self.lobby, self.username)
        # Legacy contexts could contain arbitrary fields. Never echo private data.
        safe_context = {k: v for k, v in (context or {}).items()
                        if k in {"username", "allowedValues", "preferences"}}
        try:
            context = normalize_context(safe_context, self.username, catalog)
        except ValueError:
            context = normalize_context({}, self.username, catalog)
        boards = await self.get_participant_boards()
        return {"board": next(b for b in boards if b["name"] == self.username),
                "boards": boards, "config": context, "catalog": catalog, "serverNow": self.now_ms()}

    async def get_participant_boards(self) -> list[PublicBoard]:
        names = await self.storage.get_active_usernames(self.lobby)
        names.add(self.username)
        boards = []
        for name in sorted(names):
            stored = await self.storage.get_board_state(self.lobby, name)
            boards.append(stored["public"] if stored else empty_board(name))
        return boards

    async def set_context(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            context = normalize_context(data, self.username, await self.get_catalog())
        except ValueError as error:
            raise SudokuV2Error("invalid_context", "Не удалось сохранить настройки.") from error
        if not await self.storage.save_context(self.lobby, self.username, context, self.connection_id):
            raise SudokuV2Error("connection_replaced")
        return {"config": context}

    async def set_value(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("boardName") != self.username:
            raise SudokuV2Error("board_access_denied", "Нельзя изменять чужую доску.")
        index, value = data.get("cellIndex"), data.get("value")
        if not self.valid_cell_index(index) or not await self.valid_value(value):
            raise SudokuV2Error("invalid_value", "Недопустимая клетка или значение.")
        for _ in range(8):
            board = await self.storage.get_board_state(self.lobby, self.username)
            if board is None or board["public"]["requiresGeneration"]:
                raise SudokuV2Error("board_requires_generation", "Создайте новую доску, чтобы начать игру.")
            if data.get("generationId") != board["public"]["generationId"]:
                raise SudokuV2Error("stale_generation", "Доска уже обновилась. Выберите клетку ещё раз.")
            updated = self.apply_value(board, cast(int, index), cast(BoardValue, value), self.now_ms())
            result = await self.storage.save_board_state(
                self.lobby, self.username, updated,
                (board["public"]["generationId"], board["public"]["revision"]), self.connection_id,
            )
            if result == "replaced":
                raise SudokuV2Error("connection_replaced")
            if result == "saved":
                return {"boardName": self.username, "cellIndex": index, "value": value,
                        "board": updated["public"], "serverNow": self.now_ms()}
        raise SudokuV2Error("board_busy", "Доска обновляется. Попробуйте ещё раз.")

    @staticmethod
    def apply_value(board: StoredBoard, cell_index: int, value: BoardValue, now_ms: int) -> StoredBoard:
        public = board["public"]
        if public["completed"]:
            raise SudokuV2Error("board_completed", "Доска решена. Можно начать новую игру.")
        if cell_index in public["fixedCells"]:
            raise SudokuV2Error("immutable_cell", "Исходные клетки нельзя менять.")
        if (value != "" and public["values"].get(str(cell_index)) != value
                and sum(v == value for v in public["values"].values()) >= public["size"]):
            raise SudokuV2Error("digit_limit_reached", "Все экземпляры этой цифры уже на доске.")
        updated = deepcopy(board)
        public = updated["public"]
        public["values"][str(cell_index)] = value
        public["wrongCells"] = sorted(int(i) for i, v in public["values"].items()
                                      if v != "" and v != board["solution"].get(i))
        public["completed"] = len(board["solution"]) == BOARD_CELL_COUNT and all(
            public["values"].get(i) == v for i, v in board["solution"].items()
        )
        public["finishedAt"] = now_ms if public["completed"] else None
        public["revision"] += 1
        return updated

    async def generate_board(self, data: dict[str, Any]) -> dict[str, Any]:
        difficulty, size = data.get("difficulty", "medium"), data.get("size", BOARD_SIDE)
        if not isinstance(difficulty, str) or type(size) is not int or size != BOARD_SIDE:
            raise SudokuV2Error("invalid_board", "Этот размер или сложность недоступны.")
        board = await self.get_random_board(difficulty, size)
        if board is None:
            raise SudokuV2Error("board_not_found", "Для этой сложности пока нет задач. Выберите другую.")
        public = board["public"]
        mutable = [str(i) for i in range(BOARD_CELL_COUNT) if i not in public["fixedCells"]]
        public.update(name=self.username, generationId=uuid4().hex, difficulty=difficulty,
                      startedAt=self.now_ms(), finishedAt=None, completed=False)
        public["bonuses"] = {i: choice(BONUS_DEFINITIONS)[0] for i in sample(mutable, min(6, len(mutable)))}
        if all(public["values"].get(i) == v for i, v in board["solution"].items()):
            public["completed"] = True
            public["finishedAt"] = public["startedAt"]
        for _ in range(8):
            current = await self.storage.get_board_state(self.lobby, self.username)
            previous = current["public"] if current else empty_board(self.username)
            public["revision"] = previous["revision"] + 1
            expected = (previous["generationId"], previous["revision"]) if previous["generationId"] else None
            result = await self.storage.save_board_state(self.lobby, self.username, board, expected, self.connection_id)
            if result == "replaced":
                raise SudokuV2Error("connection_replaced")
            if result == "saved":
                return {"board": public, "serverNow": self.now_ms()}
        raise SudokuV2Error("board_busy", "Доска обновляется. Попробуйте ещё раз.")

    @staticmethod
    def valid_cell_index(index: Any) -> bool:
        return type(index) is int and 0 <= index < BOARD_CELL_COUNT

    async def valid_value(self, value: Any) -> bool:
        if not valid_board_value(value):
            return False
        if value == "":
            return True
        context = await self.storage.get_context(self.lobby, self.username)
        return value in (context or {}).get("allowedValues", DEFAULT_ALLOWED_VALUES)

    @staticmethod
    async def get_random_board(difficulty: str, size: int) -> StoredBoard | None:
        board = await SudokuBoard.objects.filter(difficulty__name=difficulty).order_by("?").afirst()
        if board is None:
            return None
        cells = [cell async for cell in SudokuCell.objects.filter(board=board)
                 .order_by("number").values("number", "value", "is_empty")]
        if ({cell["number"] for cell in cells} != set(range(size * size))
                or any(type(c["value"]) is not int or not 1 <= c["value"] <= size for c in cells)):
            return None
        public = empty_board("")
        public["values"] = {str(c["number"]): "" if c["is_empty"] else c["value"] for c in cells}
        public["fixedCells"] = [c["number"] for c in cells if not c["is_empty"]]
        return {"public": public, "solution": {str(c["number"]): c["value"] for c in cells}}
