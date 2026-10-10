from typing import Any, cast

from game.models import SudokuBoard, SudokuCell

from .storage import SudokuVibeStorage


DEFAULT_ALLOWED_VALUES: list[int | str] = ["", *range(10)]
BOARD_SIDE = 9
BOARD_CELL_COUNT = BOARD_SIDE * BOARD_SIDE


class SudokuVibeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SudokuVibeService:
    def __init__(
        self,
        lobby: str,
        username: str,
        storage: SudokuVibeStorage | None = None,
        connection_id: str | None = None,
    ) -> None:
        self.lobby = lobby
        self.username = username
        self.storage = storage or SudokuVibeStorage()
        self.connection_id = connection_id

    async def get_board_data(self, data: dict[str, Any]) -> dict[str, Any]:
        context, boards = await self.storage.get_lobby_state(
            self.lobby,
            self.username,
        )
        own_board = boards.get(self.username, {})
        board_data = []
        for name, values in boards.items():
            board_data.append(
                {
                    "name": name,
                    "values": values,
                    "fixedCells": sorted(
                        await self.storage.get_fixed_cells(self.lobby, name)
                    ),
                }
            )

        own_fixed_cells = await self.storage.get_fixed_cells(
            self.lobby,
            self.username,
        )

        return {
            "board": {
                "name": self.username,
                "values": own_board,
                "fixedCells": sorted(own_fixed_cells),
            },
            "boards": board_data,
            "config": context or self.default_context(),
        }

    async def set_value(self, data: dict[str, Any]) -> dict[str, Any]:
        board_name = data.get("boardName")
        if board_name != self.username:
            raise SudokuVibeError(
                "board_access_denied",
                "User does not own this board",
            )

        cell_index = data.get("cellIndex")
        value = data.get("value")
        if not self.valid_cell_index(cell_index) or not await self.valid_value(value):
            raise SudokuVibeError(
                "invalid_value",
                "Invalid cell index or value",
            )

        valid_cell_index = cast(int, cell_index)
        valid_value = cast(int | str, value)
        update_result = await self.storage.set_cell(
            self.lobby,
            self.username,
            valid_cell_index,
            valid_value,
            self.connection_id,
        )
        if update_result == -2:
            raise SudokuVibeError(
                "connection_replaced",
                "This user is connected from another client",
            )
        if update_result == -1:
            raise SudokuVibeError(
                "board_access_denied",
                "User does not own this board",
            )
        if update_result == 0:
            raise SudokuVibeError(
                "immutable_cell",
                "Generated cell cannot be changed",
            )

        return {
            "boardName": self.username,
            "cellIndex": valid_cell_index,
            "value": valid_value,
        }

    async def set_context(self, data: dict[str, Any]) -> None:
        context = dict(data)
        context["username"] = self.username

        allowed_values = context.get("allowedValues", DEFAULT_ALLOWED_VALUES)
        if not self.valid_allowed_values(allowed_values):
            raise SudokuVibeError("invalid_context", "Invalid allowedValues")

        context["allowedValues"] = allowed_values
        saved = await self.storage.save_context(
            self.lobby,
            self.username,
            context,
            self.connection_id,
        )
        if not saved:
            raise SudokuVibeError(
                "connection_replaced",
                "This user is connected from another client",
            )

    async def generate_board(self, data: dict[str, Any]) -> dict[str, Any]:
        difficulty = data.get("difficulty", "medium")
        size = data.get("size", BOARD_SIDE)
        if not isinstance(difficulty, str) or size != BOARD_SIDE:
            raise SudokuVibeError(
                "invalid_board",
                "Unsupported board settings",
            )

        generated_board = await self.get_random_board(difficulty, size)
        if generated_board is None:
            raise SudokuVibeError("board_not_found", "Sudoku board not found")

        board_values, fixed_cells = generated_board

        replaced = await self.storage.replace_board(
            self.lobby,
            self.username,
            board_values,
            fixed_cells,
            self.connection_id,
        )
        if not replaced:
            raise SudokuVibeError(
                "connection_replaced",
                "This user is connected from another client",
            )
        context = await self.storage.get_context(self.lobby, self.username)

        return {
            "board": {
                "name": self.username,
                "values": board_values,
                "fixedCells": sorted(fixed_cells),
            },
            "config": context or self.default_context(),
        }

    def default_context(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "allowedValues": DEFAULT_ALLOWED_VALUES,
        }

    @staticmethod
    def valid_cell_index(cell_index: Any) -> bool:
        return (
            isinstance(cell_index, int)
            and not isinstance(cell_index, bool)
            and 0 <= cell_index < BOARD_CELL_COUNT
        )

    @staticmethod
    def valid_allowed_values(values: Any) -> bool:
        if not isinstance(values, list):
            return False
        return all(SudokuVibeService.valid_board_value(value) for value in values)

    @staticmethod
    def valid_board_value(value: Any) -> bool:
        return value == "" or (type(value) is int and 0 <= value <= 9)

    async def valid_value(self, value: Any) -> bool:
        if not self.valid_board_value(value):
            return False

        context = await self.storage.get_context(self.lobby, self.username)
        allowed_values = (
            context.get("allowedValues", DEFAULT_ALLOWED_VALUES)
            if context is not None
            else DEFAULT_ALLOWED_VALUES
        )
        return value in allowed_values

    @staticmethod
    async def get_random_board(
        difficulty: str,
        size: int,
    ) -> tuple[dict[str, int | str], set[int]] | None:
        board = await (
            SudokuBoard.objects.filter(difficulty__name=difficulty)
            .order_by("?")
            .afirst()
        )
        if board is None:
            return None

        cells = [
            cell
            async for cell in SudokuCell.objects.filter(board=board)
            .order_by("number")
            .values("number", "value", "is_empty")
        ]
        if len(cells) != size * size:
            return None

        values = {
            str(cell["number"]): "" if cell["is_empty"] else cell["value"]
            for cell in cells
        }
        fixed_cells = {
            cell["number"]
            for cell in cells
            if not cell["is_empty"]
        }
        return values, fixed_cells
