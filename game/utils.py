from datetime import datetime
import itertools
import pickle
import random
from itertools import islice
from copy import deepcopy
from math import sqrt
from time import time
from zoneinfo import ZoneInfo

from game.exception import SudokuException, UserDisconnect, BoardNotReqest

from .models import *

class AddHandler:

    def __init__(self) -> None:
        self.reqest_type_map = dict()

    def __call__(self, selector):
        def decorator(func):
            async def wrapper(*args, **kargs):
                return await func(*args, **kargs)
            self.reqest_type_map[selector] = wrapper
            return wrapper
        return decorator

class SudokuBoarderProxy:

    BOARD_SIDE = 9
    BOARD_SIZE = BOARD_SIDE * BOARD_SIDE

    @classmethod
    def add_random_board(cls, room_code: str, nick: str, difficulty_name: str, bonus_list: list[str], bonus_quantity = 6) -> bool:

        cls._remove_user_cells(room_code, nick)

        user_setting = cls._find_user_setting(room_code, nick)
        if user_setting is None:
            return False
        
        cells = cls._select_cells(room_code, nick, difficulty_name)
        if cells is None:
            return False

        board_id = cells[0].board_id
        user_setting.board.add(board_id)

        bonus_map = cls._create_bonus_map(board_id, bonus_list, bonus_quantity)

        user_cells = list()
        for cell_id, bonus_name in bonus_map.items():
            user_cells.append(UserCell(cell_id = cell_id, user = user_setting, bonus_name = bonus_name))

        UserCell.objects.bulk_create(user_cells)

        user_setting.time_from = datetime.now(ZoneInfo('Europe/London'))
        user_setting.time_to = None
        user_setting.save()

        return True
    
    @classmethod
    def _remove_user_cells(cls, room_code: str, nick: str) -> bool:
        try:
            user_settings = UserSetting.objects.get(lobby__code = room_code, nick = nick)
            user_settings.usercell_set.all().delete()
            return True
        except UserSetting.DoesNotExist:
            return False

    @classmethod
    def _find_user_setting(cls, room_code: str, nick: str):
        try:
            user_setting = UserSetting.objects.get(lobby__code = room_code, nick = nick)
            return user_setting
        except UserSetting.DoesNotExist:
            return None
        
    @classmethod
    def _select_cells(cls, room_code: str, nick: str, difficulty_name: str) -> QuerySet[SudokuCell]|None:
        try:
            cells: QuerySet[SudokuCell] = SudokuBoard.objects.random_for_user(room_code, nick, difficulty_name)
            
            if cells is None:
                user_setting = cls._find_user_setting(room_code, nick)
                user_setting.board.through.objects.filter(sudokuboard__difficulty__name = difficulty_name).delete()
                cells: QuerySet[SudokuCell] = SudokuBoard.objects.random_for_user(room_code, nick, difficulty_name)

            return cells

        except (UserSetting.DoesNotExist, AttributeError):
            return None
    
    @classmethod
    def _create_bonus_map(cls, boarder_id: int, bonus_list: list[str], quantity: int) -> dict[int, str]:
        empty_cells_id: list[SudokuCell] = SudokuCell.objects.get_random_empty_cell_id(boarder_id, quantity)
        bonuses = random.choices(bonus_list, k = len(empty_cells_id))

        # TODO: change string as value on link, maybe recreate bonus_list as enum

        return {
            cell_id: bonus_name for cell_id, bonus_name in zip(empty_cells_id, bonuses)
        }

    @classmethod
    def _get_user_setting(cls, room_code: str, nick: str):
        user_setting = cls._find_user_setting(room_code, nick)
        if user_setting is None:
            raise UserDisconnect(room_code, nick)
        
        return user_setting

    @classmethod
    def _get_user_setting_and_last_board(cls, room_code: str, nick: str) -> tuple[UserSetting, SudokuBoard]:
        user_setting = cls._get_user_setting(room_code, nick)

        lastboard_id = user_setting.board.through.objects.filter(usersetting = user_setting).last()

        if lastboard_id is None:
            raise BoardNotReqest(room_code, nick)
        
        last_board: SudokuBoard = lastboard_id.sudokuboard    
        return user_setting, last_board
    
    @classmethod
    def _find_user_setting_and_last_board(cls, room_code: str, nick: str) -> tuple[UserSetting, SudokuBoard]:
        user_setting = cls._get_user_setting(room_code, nick)

        lastboard_id = user_setting.board.through.objects.filter(usersetting = user_setting).last()
        if lastboard_id is None:
            return user_setting, None
        last_board: SudokuBoard = lastboard_id.sudokuboard

        # if last_board is None:
        #     raise BoardNotReqest(room_code, nick)
        
        return user_setting, last_board

    @classmethod
    def delete_user(self, room_code, nick) -> bool:
        """
        delete user from lobby

        :param room_code: room code
        :param nick: user's nick in room
        :return: if user was last in lobby and lobby remove, return True. Else return False 
        """
        try:
            UserSetting.objects.filter(lobby__code = room_code, nick = nick).delete()
            count_channels = UserSetting.objects.filter(lobby__code = room_code).count()
            if count_channels == 0:
                LobbySetting.objects.get(code = room_code).delete()
                return True
            return False
        except (UserSetting.DoesNotExist, LobbySetting.DoesNotExist):
            return False

    @classmethod
    def set_value(cls, room_code: str, nick: str, value: int, cell_number: int) -> tuple[bool|None, str|None]:
        """
        Set value in database

        :param room_code: room code
        :param nick: user's nick in room
        :param value: value sent by user
        :param cell_number: cell number for value
        :return:    (None, None) - if value not change
                    (True, None) - if value is truth or zero, but bonus not exist
                    (True, str) - if value is truth and bonus exist
                    (False, None) - if value is wrong
        """
        user_setting, last_board = cls._get_user_setting_and_last_board(room_code, nick)
        
        cell: SudokuCell = last_board.sudokucell_set.get(number = cell_number)
        if not cell.is_empty:
            return (False, None)
        
        user_cell, created = UserCell.objects.get_or_create(user = user_setting, cell = cell)
        if user_cell.value == value:
            return (None, None)
        
        is_equal = cell.value == value or value == 0
        was_equal = not created and user_cell.was_equal

        if value != user_cell.value:
            if is_equal and not was_equal and value != 0:
                user_cell.was_equal = True
            user_cell.value = value
            user_cell.save()
        
        if not is_equal or was_equal:
            return (is_equal, None)
        
        return (is_equal, user_cell.bonus_name)
    
    @classmethod
    def get_clean_board(cls, room_code: str, nick: str) -> dict[str, int]:
        user_setting, last_board = cls._find_user_setting_and_last_board(room_code, nick)

        if last_board is None:
            return None

        clean_board = dict()
        cells = SudokuCell.objects.filter(Q(board = last_board) & (Q(is_empty = False) | Q(usercell__user = user_setting)))

        for cell in cells:

            if not cell.is_empty:
                clean_board[str(cell.number)] = cell.value
            else:
                user_cell: UserCell|None = cell.usercell_set.first()
                clean_board[str(cell.number)] = user_cell.value

        return clean_board
            
    @classmethod
    def get_bonus_map(cls, room_code: str, nick: str) -> dict[str, str]:
        bonus_cells = UserCell.objects.filter(Q(user__nick = nick) & Q(user__lobby__code = room_code) & ~Q(bonus_name = None)).values('bonus_name', 'cell__number')
        bonus_map = dict()

        for bonus_cell in bonus_cells:
            bonus_map[str(bonus_cell['cell__number'])] = bonus_cell['bonus_name']

        return bonus_map

    @classmethod
    def get_wrong_answers(cls, room_code: str, nick: str) -> list[int]:
        wrong_cell = UserCell.objects.filter(Q(user__nick = nick) & Q(user__lobby__code = room_code) & ~Q(value = 0) & ~Q(value = F('cell__value'))).values('cell__number')
        wrong_answer_list = list(map(lambda wrong_cell: wrong_cell['cell__number'], wrong_cell))
        return wrong_answer_list

    @classmethod
    def get_static_cell_number(cls, room_code: str, nick: str) -> list[int]:
        _, last_board = cls._find_user_setting_and_last_board(room_code, nick)
        if last_board is None:
            return None
        static_cells = SudokuCell.objects.filter(board = last_board, is_empty = False).values('number')
        static_answer_list = list(map(lambda wrong_cell: wrong_cell['number'], static_cells))
        return static_answer_list

    @classmethod
    def get_time_from(cls, room_code: str, nick: str) -> int|None:
        user_setting = cls._get_user_setting(room_code, nick)
        time_from = user_setting.time_from
        if time_from is None:
            return None
        
        time_from = int(time_from.timestamp())
        return time_from

    @classmethod
    def get_time_to(cls, room_code: str, nick: str) -> int|None:
        user_setting = cls._get_user_setting(room_code, nick)
        time_to = user_setting.time_to
        if time_to is None:
            return None
        
        time_to = int(time_to.timestamp())
        return time_to

    @classmethod
    def finish(cls, room_code: str, nick: str) -> int|None:
        try:
            user_setting, last_board = cls._get_user_setting_and_last_board(room_code, nick)
        except SudokuException:
            return None
        
        if user_setting.time_to is not None:
            return int(user_setting.time_to.timestamp())

        rigth_count = SudokuCell.objects.filter(Q(board = last_board) & ( Q(is_empty = False) | Q(usercell__user = user_setting) & Q(usercell__value = F('value')))).count()
        if rigth_count == cls.BOARD_SIZE:
            finis_time = datetime.now(ZoneInfo('Europe/London'))
            user_setting.time_to = finis_time
            user_setting.save()

        return int(user_setting.time_to.timestamp())

    @classmethod
    def get_room_info(cls, room_code):
        info_map = dict()

        lobby_nicks = list(map(lambda user_setting: user_setting['nick'], UserSetting.objects.filter(lobby__code = room_code).values('nick')))
        for nick in lobby_nicks:

            # TODO: in one query if posible

            info_map[nick] = {
                'value': cls.get_clean_board(room_code, nick),
                'bonus': cls.get_bonus_map(room_code, nick),
                'static_answer': cls.get_static_cell_number(room_code, nick),
                'wrong_answer': cls.get_wrong_answers(room_code, nick),
                'time_from': cls.get_time_from(room_code, nick),
                'time_to': cls.get_time_to(room_code, nick),
            }

        return info_map

##############################
#                            #
#      Sudoku generator      #
#                            #
##############################
# https://stackoverflow.com/a/56581709/19375794

class Sudoku:
    def __init__(self, side: int, max_empties = 60):
        self.side = side
        self.max_empties = max_empties
        self.empty_cell = 0

        self.base = int(sqrt(side))
        self.board = [[0 for _ in range(side)] for _ in range(side)]

        self._fill_values()

        self._clean_board = None
    
    def _fill_values(self):
        self._fill_remaining(0, 0)

    def _is_safe(self, row, col, num):
        return (self._is_use_in_row(row, num) and self._is_use_in_col(col, num) and self._is_use_un_box(row - row % self.base, col - col % self.base, num))
    
    def _is_use_in_row(self, row, num):
        for col in range(self.side):
            if self.board[row][col] == num:
                return False
        return True
    
    def _is_use_in_col(self, col, num):
        for row in range(self.side):
            if self.board[row][col] == num:
                return False
        return True
        
    def _is_use_un_box(self, row, col, num):
        for row_inner in range(self.base):
            for col_inner in range(self.base):
                if self.board[row + row_inner][col + col_inner] == num:
                    return False
        return True
   
    def _fill_remaining(self, i, j):
        # Check if we have reached the end of the matrix
        if i == self.side - 1 and j == self.side:
            return True
    
        # Move to the next row if we have reached the end of the current row
        if j == self.side:
            i += 1
            j = 0
    
        # Skip cells that are already filled
        if self.board[i][j] != 0:
            return self._fill_remaining(i, j + 1)
    
        # Try filling the current cell with a valid value
        posible_value = list(range(1, self.side + 1))
        random.shuffle(posible_value)
        for num in posible_value:
            if self._is_safe(i, j, num):
                self.board[i][j] = num
                if self._fill_remaining(i, j + 1):
                    return True
                self.board[i][j] = 0
        
        # No valid value was found, so backtrack
        return False

    @property
    def clean_board(self):
        if self._clean_board is None:
            self.clear_board()
        return self._clean_board
    
    def clear_board(self, max_empties = None, attempts = 9):
        self._clean_board = deepcopy(self.board)
        self.max_empties = max_empties or self.max_empties

        cell_order = list(range(self.side ** 2))
        random.shuffle(cell_order)

        while attempts > 0 and len(cell_order) > 0 and self.max_empties > self.empty_cell:

            pos = cell_order.pop()
            row, col = (pos // self.side), (pos % self.side)

            backup = self._clean_board[row][col]
            self._clean_board[row][col]=0

            solved  = [*islice(self.short_sudoku_solve(self._clean_board),2)]
            if len(solved)>1:
                self._clean_board[row][col]=backup
                attempts -= 1
            else:
                self.empty_cell += 1
        
        return self.empty_cell
    
    def fill_up(self, need_empty):
        order_fill = list(range(self.side ** 2))
        random.shuffle(order_fill)
        while need_empty < self.empty_cell:

            pos = order_fill.pop()
            row, col = pos // self.side, pos % self.side
            if self.clean_board[row][col] == 0:
                self.clean_board[row][col] = self.board[row][col]
                self.empty_cell -= 1

    @classmethod
    def short_sudoku_solve(cls, board):
        side   = len(board)
        base   = int(side**0.5)
        board  = [n for row in board for n in row ]
        blanks = [i for i,n in enumerate(board) if n==0 ]
        cover  = { (n,p):{*zip([2*side+r, side+c, r//base*base+c//base],[n]*(n and 3))}
                    for p in range(side*side) for r,c in [divmod(p,side)] for n in range(side+1) }
        used   = set().union(*(cover[n,p] for p,n in enumerate(board) if n))
        placed = 0
        while placed>=0 and placed<len(blanks):
            pos        = blanks[placed]
            used      -= cover[board[pos],pos]
            board[pos] = next((n for n in range(board[pos]+1,side+1) if not cover[n,pos]&used),0)
            used      |= cover[board[pos],pos]
            placed    += 1 if board[pos] else -1
            if placed == len(blanks):
                solution = [board[r:r+side] for r in range(0,side*side,side)]
                yield solution
                placed -= 1

    @classmethod
    def generate_sudoku_with_setting(cls, base: int, limit_reqest: list[tuple[int, int, int]]) -> tuple[list[list[int]], list[list[int]], int]:
        """
        Generate one board on request setting

        :param base: inner box side
        :param limit_reqest: array of difficulties
            difficult[0] - required number of tables
            difficult[1] - min empty limit
            difficult[2] - pk in Difficulty table 
        :return:
            tuple(
                list[list[int]] Sudoku board (base**2)x(base**2) size with empty cell by one request,
                list[list[int]] Filled board,
                id              pk of difficulty
            )
        """
        side = base * base
        sudoku = cls(side)

        select_difficult = None
        for difficult_index in range(len(limit_reqest) - 1, -1, -1):
            if limit_reqest[difficult_index][0] > 0 and sudoku.empty_cell == 0:
                sudoku.clear_board(limit_reqest[difficult_index][1])

            if sudoku.empty_cell != 0:
                if (difficult_index == 0 or limit_reqest[difficult_index - 1][1] < sudoku.empty_cell) and limit_reqest[difficult_index][0] > 0:
                    limit_reqest[difficult_index] = cast(tuple[int, int, int], tuple(
                        value - 1 if index == 0 else value for index, value in enumerate(limit_reqest[difficult_index])
                    ))
                    select_difficult = limit_reqest[difficult_index]
                    break
        
        if select_difficult is not None:
            if select_difficult[1] < sudoku.empty_cell:
                sudoku.fill_up(select_difficult[1])

            return sudoku.clean_board, sudoku.board, select_difficult[2]
        
        return cls.generate_sudoku_with_setting(base, limit_reqest)
