import itertools
import pickle
import random
from itertools import islice
from copy import deepcopy
from math import sqrt

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

class SudokuMap:
    SIDE_SIZE = 9
    BOARD_SIZE = SIDE_SIZE * SIDE_SIZE
    _sudoku_map = dict()

    SOLUTION_BOARD = 'solution'
    CLEAN_BOARD = 'clean_board'
    BONUS_MAP = 'bonus'

    def __check_exist_user(func):
        def wrapper(self, code: str, nick: str, *arg, **kwargs):
            room = SudokuMap._sudoku_map.get(code)
            if not room:
                return
            user = room.get(nick)
            if not user:
                return
            return func(self, room, user, *arg, **kwargs)
        return wrapper

    @classmethod
    def set(cls, room_code: str, nick: str, clean_board: list[list[int]]|None = None, solution_board: QuerySet[SudokuCell]|None = None, bonus_map: dict[int, str]|None = None) -> bool:
        room = cls._sudoku_map.get(room_code, False)
        if not room:
            room = dict()
            cls._sudoku_map[room_code] = room

        user = room.get(nick, False)
        if not user:
            user = dict()
            room[nick] = user

        user[cls.SOLUTION_BOARD] = solution_board
        user[cls.CLEAN_BOARD] = clean_board
        user[cls.BONUS_MAP] = bonus_map

        return True
    
    @classmethod
    def remove(cls, code, nick) -> bool:
        room: dict = cls._sudoku_map.get(code, False)
        if not room:
            return True
        
        room.pop(nick, None)

        if len(room) == 0:
            del cls._sudoku_map[code]

        return True
    
    @classmethod
    def get_by_room(cls, code, with_solution = False) -> dict|None:
        room = cls._sudoku_map.get(code, None)
        if room: 
            room = deepcopy(room)
            if not with_solution:
                for boards in room.values():
                    del boards[cls.SOLUTION_BOARD] 
        return room
    
    @classmethod
    @__check_exist_user
    def get_by_nick(cls, code: str, nick: str, with_solution: bool = False) -> dict|None:
        
        user = deepcopy(nick)

        if not with_solution:
            del user[cls.SOLUTION_BOARD]
            del user[cls.BONUS_MAP]
        return user
    
    @classmethod
    @__check_exist_user
    def get_bonus_for_send(cls, code: str, nick: str) -> dict[str, str]:
        raw_bonus_map: dict[int, str]|None = nick.get(cls.BONUS_MAP)
        if not raw_bonus_map:
            return None
        
        return {str(key): value for key, value in raw_bonus_map.items()}
    
    @classmethod
    def get_by_room_info_type(cls, code) -> dict|None:
        room = cls._sudoku_map.get(code)
        if room is None:
            return room
        
        info_map = dict()

        for nick, boards in room.items():
            info_map[nick] = {
                'value': convert_clean_board_to_map(boards[cls.CLEAN_BOARD]) if boards[cls.CLEAN_BOARD] else None,
                'bonus': cls.get_bonus_for_send(code, nick)
            }

        return info_map
    
    @classmethod
    @__check_exist_user
    def get_bonus(cls, code: str, nick: str, cell_number) -> str|None:
        bonus_map = nick.get(cls.BONUS_MAP)
        if not bonus_map:
            return
        return bonus_map.get(cell_number)
    
    @classmethod
    @__check_exist_user
    def pop_bonus(cls, code: str, nick: str, cell_number: int) -> str|None:
        bonus_map = nick.get(cls.BONUS_MAP)
        if not bonus_map:
            return
        return bonus_map.pop(cell_number, None)

    @classmethod
    @__check_exist_user
    def equival(cls, code: str, nick: str, value: int, cell_number: int, save: bool = True) -> bool|None:
        """
        compares solution and digit by user

        :param code: room code
        :param nick: user's nick in room
        :param value: user get value for compare with solution
        :param cell_number: cell number in board for compare
        :param save: after compare save in database
        :return: matches value and solution or None if board not exist 
        """


        solution_board = nick.get(cls.SOLUTION_BOARD, None)

        if solution_board is None:
            return None
        
        is_equel = value == 0 or solution_board.filter(value = value, number = cell_number).exists()

        if save:
            row = cell_number // cls.SIDE_SIZE
            column = cell_number % cls.SIDE_SIZE
            nick[cls.CLEAN_BOARD][row][column] = value

        return is_equel

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
    def generate_sudoku_with_setting(cls, base, limit_reqest):
        """
        Generate one board on request setting

        :param base: inner box side
        :param limit_reqest: array of difficulties
            difficult[0] - difficulty name
            difficult[1] - required number of tables
            difficult[2] - min empty limit
            difficult[3] - pk in Difficulty table 
        :return: list[list[int]] Sudoku board (base**2)x(base**2) size with empty cell by one request
        """
        side = base * base
        sudoku = cls(side)

        select_difficult = None
        for difficult_index in range(len(limit_reqest) - 1, -1, -1):
            if limit_reqest[difficult_index][1] > 0 and sudoku.empty_cell == 0:
                sudoku.clear_board(limit_reqest[difficult_index][2])

            if sudoku.empty_cell != 0:
                if (difficult_index == 0 or limit_reqest[difficult_index - 1][2] < sudoku.empty_cell) and limit_reqest[difficult_index][1] > 0:
                    select_difficult = limit_reqest[difficult_index]
                    select_difficult[1] -= 1
                    break
        
        if select_difficult is not None:
            if select_difficult[2] < sudoku.empty_cell:
                sudoku.fill_up(select_difficult[2])

            return sudoku.clean_board, sudoku.board, select_difficult[0], select_difficult[3]
        
        return cls.generate_sudoku_with_setting(base, limit_reqest)

def convert_clean_board_to_map(clean_board: list[list[int]]) -> dict[int, int]|None:
    board_info: dict = dict()
    side_lenght = len(clean_board)
    squares_quantity = side_lenght * side_lenght

    try:
        for index in range(squares_quantity):
            row_index = index // side_lenght
            column_index = index % side_lenght
            if clean_board[row_index][column_index] != 0:
                board_info[str(index)] = clean_board[row_index][column_index]
    except IndexError:
        return None

    return board_info

def create_bonus_map(board: list[list[int]], bonus_list, k = 6):
    empty_cells = [index for index, value in enumerate(itertools.chain.from_iterable(board)) if value == 0]
    cells_index = random.sample(empty_cells, k = k)
    bonuses = random.choices(bonus_list, k = k)

    # TODO: change string as value on link, maybe recreate bonus_list as enum

    return {
        cell_index: bonus_name for cell_index, bonus_name in zip(cells_index, bonuses)
    }