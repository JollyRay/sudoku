from django.core.management.base import BaseCommand
from django.db.models import Count

from game.utils import Sudoku
from game.models import Difficulty, SudokuBoard, SudokuCell

class Command(BaseCommand):

    MIN_BOARD_NEED = 10

    def handle(self, *args, **options) -> None:
        self._create_start_board()

    def _create_start_board(self, base: int = 3) -> None:

        # Init settings

        difficulty_info = Difficulty.objects.values('name', 'top_limit', 'pk').order_by('top_limit').annotate(count = Count('sudokuboard'))
        limit_reqest = []
        for difficulty in difficulty_info:
            limit_reqest.append((
                max(0, self.MIN_BOARD_NEED - difficulty['count']),
                difficulty['top_limit'], 
                difficulty['pk'], 
            ))
        limit_reqest.sort(key = lambda difficulty: difficulty[2])

        # Fill

        while (limit_reqest[0][0] or limit_reqest[1][0] or limit_reqest[2][0]):

            data = Sudoku.generate_sudoku_with_setting(base, limit_reqest)
            self._add_board(*data, limit_reqest, size = base * base)

    def _add_board(self, clean_board: list[list[int]], solution_board: list[list[int]], difficulty_id: int, limit_reqest: list[tuple[int, int, int]], size: int) -> None:
        message = ' '.join((f'LvL{param[2]}: {max(0, self.MIN_BOARD_NEED - param[0])}/{self.MIN_BOARD_NEED}' for param in limit_reqest))
        self.stdout.write(message + '   ')

        board_in_bd = SudokuBoard.objects.create(difficulty_id = difficulty_id)
        SudokuCell.objects.bulk_create([
            SudokuCell(
                board = board_in_bd,
                number = row * size + col,
                value = value,
                is_empty = clean_board[row][col] == 0)
                
                for row, line in enumerate(solution_board) for col, value in enumerate(line)
        ])
        