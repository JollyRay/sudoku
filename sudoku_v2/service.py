from copy import deepcopy
from random import choice, sample
from time import time
from typing import Any, cast
from uuid import uuid4

from django.templatetags.static import static
from game.models import Difficulty, SudokuBoard, SudokuCell

from .constants import (
    BOARD_SIDE, BONUS_DEFINITIONS, allowed_values,
    SUPPORTED_SIZES, SYMBOL_PRESET_DEFINITIONS,
)
from .storage import BoardValue, PublicBoard, StoredBoard, SudokuV2Storage, empty_board
from .bonuses import BonusRequest
from .bonus_service import BonusService
from .user_context import normalize_context, valid_board_value, valid_cell_index
from .twitch.registry import TwitchRegistry


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

    async def get_twitch_status(self, data):
        registry=TwitchRegistry(self.storage)
        epoch=await self.storage.get_room_epoch(self.lobby)
        active=bool(await self.storage.redis.get(registry.prefix+':active-worker'))
        bindings=[]
        for binding in await registry.list_active():
            if binding['lobby']!=self.lobby or binding['roomEpoch']!=epoch: continue
            status=await registry.get_status(binding)
            bindings.append({key:binding[key] for key in ('channel','owner','bindingId','cooldownSeconds')}
                | {'status':status['status'] if status else ('connecting' if active else 'disabled'),
                   'reason':status['reason'] if status else ('join' if active else 'worker_unavailable')})
        states={binding['status'] for binding in bindings}
        worker_status=next((state for state in ('auth_error','error','connecting','connected') if state in states),'disabled')
        return {'requestId':data.get('requestId'),'bindings':bindings,'workerStatus':worker_status,'serverNow':self.now_ms()}

    async def connect_twitch(self, data):
        await TwitchRegistry(self.storage).register(self.lobby,self.username,self.connection_id,
            data.get('channel'),data.get('cooldownSeconds',0))
        return await self.get_twitch_status(data)

    async def disconnect_twitch(self, data):
        await TwitchRegistry(self.storage).disconnect(self.lobby,self.username,self.connection_id,data.get('channel'))
        return await self.get_twitch_status(data)

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
        boards = await self.get_participant_boards()
        own_board = next(b for b in boards if b['name'] == self.username)
        context = await self._restore_context(context, own_board['size'], catalog=catalog)
        return {"board": own_board,
                "boards": boards, "config": context, "catalog": catalog, "serverNow": self.now_ms()}

    async def _restore_context(self, context, size, *, catalog=None, reset_values=False):
        # Legacy contexts could contain arbitrary fields. Never echo private data.
        fields = {'username', 'preferences'}
        if not reset_values:
            fields.add('allowedValues')
        safe_context = {key: value for key, value in (context or {}).items() if key in fields}

        async def normalize(candidate):
            # Generation reads the catalog again on fallback, as it did before.
            current_catalog = catalog if catalog is not None else await self.get_catalog()
            return normalize_context(candidate, self.username, current_catalog, board_size=size)

        try:
            return await normalize(safe_context)
        except ValueError:
            return await normalize({})

    async def get_participant_boards(self) -> list[PublicBoard]:
        names = await self.storage.get_active_usernames(self.lobby)
        names.add(self.username)
        boards = []
        for name in sorted(names):
            stored = await self.storage.get_board_state(self.lobby, name)
            boards.append(stored["public"] if stored else empty_board(name))
        return boards

    async def set_context(self, data: dict[str, Any]) -> dict[str, Any]:
        catalog = await self.get_catalog()
        for _ in range(8):
            stored = await self.storage.get_board_state(self.lobby, self.username)
            board = stored['public'] if stored else empty_board(self.username)
            if data.get('generationId') != board['generationId']:
                raise SudokuV2Error('stale_context', 'Доска изменилась. Обновляем настройки.')
            try:
                context = normalize_context({k: v for k, v in data.items() if k != 'generationId'}, self.username, catalog, board_size=board['size'])
            except ValueError as error:
                raise SudokuV2Error("invalid_context", "Не удалось сохранить настройки.") from error
            expected = (board['generationId'], board['revision']) if board['generationId'] else None
            result = await self.storage.save_context_for_board(self.lobby, self.username, context, expected, self.connection_id)
            if result == 'replaced':
                raise SudokuV2Error("connection_replaced")
            if result == 'saved':
                return {"config": context}
        raise SudokuV2Error('board_busy', 'Доска обновляется. Попробуйте ещё раз.')

    async def set_value(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("boardName") != self.username:
            raise SudokuV2Error("board_access_denied", "Нельзя изменять чужую доску.")
        index, value = data.get("cellIndex"), data.get("value")
        bonus_service, event_id = BonusService(self.storage), uuid4().hex
        for _ in range(8):
            board = await self.storage.get_board_state(self.lobby, self.username)
            if board is None or board["public"]["requiresGeneration"]:
                raise SudokuV2Error("board_requires_generation", "Создайте новую доску, чтобы начать игру.")
            size = board['public']['size']
            if not valid_cell_index(index, size) or not await self.valid_value(value, size):
                raise SudokuV2Error("invalid_value", "Недопустимая клетка или значение.")
            if data.get("generationId") != board["public"]["generationId"]:
                raise SudokuV2Error("stale_generation", "Доска уже обновилась. Выберите клетку ещё раз.")
            now = self.now_ms()
            updated = self.apply_value(board, cast(int, index), cast(BoardValue, value), now)
            public, event = board['public'], None
            kind = public['bonuses'].get(str(index))
            if kind and value == board['solution'].get(str(index)) and index not in public['consumedBonusCells']:
                updated['public']['consumedBonusCells'] = sorted([*public['consumedBonusCells'], index])
                targets, expected = await bonus_service.collect_targets(self.lobby, self.username, ['*'])
                if targets:
                    targets, event = bonus_service.prepare(targets, BonusRequest(kind, ['*'], {}),
                        event_id, now, {'type': 'cell', 'name': self.username})
                    # The consumed marker on the source is part of the same public delta.
                    event['targets'].append(updated['public'])
                targets[self.username] = updated
                expected[self.username] = (public['generationId'], public['revision'], self.connection_id)
                result = await self.storage.commit_boards(self.lobby, targets, expected)
                if result != 'saved' and await self.storage.get_presence_token(self.lobby, self.username) != self.connection_id:
                    result = 'replaced'
            else:
                result = await self.storage.save_board_state(
                    self.lobby, self.username, updated,
                    (public['generationId'], public['revision']), self.connection_id,
                )
            if result == "replaced":
                raise SudokuV2Error("connection_replaced")
            if result == "saved":
                response = {"boardName": self.username, "cellIndex": index, "value": value,
                            "board": updated["public"], "serverNow": self.now_ms()}
                if event:
                    response['_bonus_event'] = event
                return response
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
        public["completed"] = len(board["solution"]) == public['size'] ** 2 and all(
            public["values"].get(i) == v for i, v in board["solution"].items()
        )
        public["finishedAt"] = now_ms if public["completed"] else None
        public["revision"] += 1
        return updated

    async def generate_board(self, data: dict[str, Any]) -> dict[str, Any]:
        difficulty, size = data.get("difficulty", "medium"), data.get("size", BOARD_SIDE)
        if not isinstance(difficulty, str) or type(size) is not int or size not in SUPPORTED_SIZES:
            raise SudokuV2Error("invalid_board", "Этот размер или сложность недоступны.")
        board = await self.get_random_board(difficulty, size)
        if board is None:
            raise SudokuV2Error("board_not_found", "Для этой сложности пока нет задач. Выберите другую.")
        public = board["public"]
        mutable = [str(i) for i in range(size * size) if i not in public["fixedCells"]]
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
            old_context = await self.storage.get_context(self.lobby, self.username)
            context = await self._restore_context(old_context, size, reset_values=True)
            context['preferences'].update(size=size, difficulty=difficulty)
            result = await self.storage.save_board_state(self.lobby, self.username, board, expected, self.connection_id,
                                                        context=context, expected_context=old_context)
            if result == "replaced":
                raise SudokuV2Error("connection_replaced")
            if result == "saved":
                return {"board": public, "config": context, "serverNow": self.now_ms()}
        raise SudokuV2Error("board_busy", "Доска обновляется. Попробуйте ещё раз.")

    async def valid_value(self, value: Any, size: int = 9) -> bool:
        if not valid_board_value(value, size):
            return False
        if value == "":
            return True
        context = await self.storage.get_context(self.lobby, self.username)
        return value in (context or {}).get("allowedValues", allowed_values(size))

    @staticmethod
    async def get_random_board(difficulty: str, size: int) -> StoredBoard | None:
        board = await SudokuBoard.objects.for_size(size).filter(difficulty__name=difficulty).order_by("?").afirst()
        if board is None:
            return None
        cells = [cell async for cell in SudokuCell.objects.filter(board=board)
                 .order_by("number").values("number", "value", "is_empty")]
        if ({cell["number"] for cell in cells} != set(range(size * size))
                or any(type(c["value"]) is not int or not 1 <= c["value"] <= size for c in cells)):
            return None
        public = empty_board("", size)
        public["values"] = {str(c["number"]): "" if c["is_empty"] else c["value"] for c in cells}
        public["fixedCells"] = [c["number"] for c in cells if not c["is_empty"]]
        return {"public": public, "solution": {str(c["number"]): c["value"] for c in cells}}
