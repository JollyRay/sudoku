import itertools
import pickle
import random
from itertools import islice
from copy import deepcopy

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
    def equival(cls, code: str, nick: str, value: int, cell_number: int, save: bool = True) -> bool:
        
        is_equel = value == 0 or nick[cls.SOLUTION_BOARD].filter(value = value, number = cell_number).exists()

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

def shortSudokuSolve(board):
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

def _generate_full_board(base = 3):
    side = base*base
    def pattern(r,c): return (base*(r%base)+r//base+c)%side
    def shuffle(s): return random.sample(s,len(s)) 

    rBase = range(base) 
    rows  = [ g*base + r for g in shuffle(rBase) for r in shuffle(rBase) ] 
    cols  = [ g*base + c for g in shuffle(rBase) for c in shuffle(rBase) ]
    nums  = shuffle(range(1,base*base+1))

    board = [ [nums[pattern(r,c)] for c in cols] for r in rows ]

    return board

def _clean_board(board, max_empties = 60, side = 9, attempts = 9):
    cell_order = list(range(side * side))
    random.shuffle(cell_order)
    empty_cell = 0

    while attempts > 0 and len(cell_order) > 0 and max_empties > empty_cell:

        pos = cell_order.pop()
        row, col = (pos // side), (pos % side)

        backup = board[row][col]
        board[row][col]=0

        solved  = [*islice(shortSudokuSolve(board),2)]
        if len(solved)>1:
            board[row][col]=backup
            attempts -= 1
        else:
            empty_cell += 1
    
    return empty_cell

def generate_sudoku(base = 3) -> tuple[list[list[int]]]:
    solution_board = _generate_full_board(base)
    clean_board = deepcopy(solution_board)
    _clean_board(clean_board)

    return (solution_board, clean_board)

def generate_sudoku_with_setting(base, limit_reqest):
    side = base * base
    solution_board = _generate_full_board(base)
    clean_board = pickle.loads(pickle.dumps(solution_board, -1))

    empty_quantity = -1
    select_difficult = None
    for difficult_index in range(len(limit_reqest) - 1, -1, -1):
        if limit_reqest[difficult_index][1] > 0 and empty_quantity == -1:
            empty_quantity = _clean_board(clean_board, max_empties = limit_reqest[difficult_index][2], side = side)

        if empty_quantity != -1:
            if (difficult_index == 0 or limit_reqest[difficult_index - 1][2] < empty_quantity) and limit_reqest[difficult_index][1] > 0:
                select_difficult = limit_reqest[difficult_index]
                select_difficult[1] -= 1
                break
    
    if select_difficult is not None:
        if select_difficult[2] < empty_quantity:
            _fill_up(clean_board, solution_board, select_difficult[2], empty_quantity, side)

        return clean_board, solution_board, select_difficult[0], select_difficult[3]
    
    return generate_sudoku_with_setting(base, limit_reqest)

def _fill_up(clean_board: list[list[int]], solution_board: list[list[int]], need_empty, have_empty, side = 9):
    order_fill = list(range(81))
    random.shuffle(order_fill)
    while need_empty < have_empty:

        pos = order_fill.pop()
        row, col = pos // side, pos % side
        if clean_board[row][col] == 0:
            clean_board[row][col] = solution_board[row][col]
            have_empty -= 1


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