from django.core.management.base import BaseCommand
from django.db.models import Count

from game.utils import generate_sudoku_with_setting
from game.models import Difficulty, SudokuBoard, SudokuCell

class Command(BaseCommand):

    MIN_BOARD_NEED = 100

    def handle(self, *args, **options):
        self._create_start_board()

    def _create_start_board(self, base: int = 3):

        # Init settings

        difficulty_info = Difficulty.objects.values('name', 'top_limit', 'pk').order_by('top_limit').annotate(count = Count('sudokuboard'))
        limit_reqest = []
        for difficulty in difficulty_info:
            limit_reqest.append([
                difficulty['name'],
                max(0, self.MIN_BOARD_NEED - difficulty['count']),
                difficulty['top_limit'], 
                difficulty['pk'], 
            ])
        limit_reqest.sort(key = lambda difficulty: difficulty[2])

        # Fill

        while (limit_reqest[0][1] or limit_reqest[1][1] or limit_reqest[2][1]):

            data = generate_sudoku_with_setting(base, limit_reqest)
            self._add_board(*data, limit_reqest, size = base * base)

    def _add_board(self, clean_board, solution_board, difficulty, difficulty_id, limit_reqest, size):
        message = ' '.join((f'{param[0]}: {max(0, self.MIN_BOARD_NEED - param[1])}/{self.MIN_BOARD_NEED}' for param in limit_reqest))
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
        