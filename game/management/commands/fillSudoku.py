"""Fill independent size/difficulty quotas with proven unique puzzles."""
from math import isfinite
from random import Random
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.generator import GenerationBudgetExceeded, generate_puzzle, count_solutions
from game.models import Difficulty, SudokuBoard, SudokuCell


class Command(BaseCommand):
    help = 'Generate Sudoku (use --settings=sudoku_v2.generator_settings outside tests).'

    def add_arguments(self, parser):
        parser.add_argument('--sizes', nargs='+', type=int, default=[9, 16])
        parser.add_argument('--minimum', type=int, default=10)
        parser.add_argument('--seed', type=int)
        parser.add_argument('--max-seconds', type=float, default=30)

    def handle(self, *args, **options):
        sizes, minimum, budget = options['sizes'], options['minimum'], options['max_seconds']
        if any(size not in (9, 16) for size in sizes) or minimum < 0 or not isfinite(budget) or budget <= 0:
            raise CommandError('Use sizes 9/16, a nonnegative minimum and a positive finite time budget')
        for name, limit in zip(Difficulty.DifficultyName.values, Difficulty.DifficultyTopLimit.values):
            Difficulty.objects.get_or_create(name=name, defaults={'top_limit': limit})
        difficulties = list(Difficulty.objects.order_by('top_limit', 'pk'))
        rng = Random(options['seed'])
        for size in dict.fromkeys(sizes):
            previous = 0
            for difficulty in difficulties:
                lower, upper = previous + 1, difficulty.top_limit * size * size // 81
                previous = upper
                if not 1 <= lower <= upper <= size * size:
                    raise CommandError(f'Invalid difficulty range: {difficulty.name}')
                count = self.valid_count(size, difficulty.pk, lower, upper, budget)
                for _ in range(max(0, minimum - count)):
                    try:
                        generated = generate_puzzle(size, lower, upper, rng, max_seconds=budget)
                    except GenerationBudgetExceeded as exc:
                        raise CommandError(f'{size}x{size} {difficulty.name}: generation budget exhausted') from exc
                    with transaction.atomic():
                        board = SudokuBoard.objects.create(difficulty=difficulty)
                        SudokuCell.objects.bulk_create([
                            SudokuCell(board=board, number=r * size + c, value=value,
                                       is_empty=generated.puzzle[r][c] == 0)
                            for r, row in enumerate(generated.solution) for c, value in enumerate(row)
                        ])
                    count += 1
                    blanks = sum(value == 0 for row in generated.puzzle for value in row)
                    self.stdout.write(f'{size}x{size} {difficulty.name}: {count}/{minimum}, {blanks} blanks')

    @staticmethod
    def valid_count(size, difficulty_id, lower, upper, budget):
        count = 0
        boards = SudokuBoard.objects.for_size(size).filter(difficulty_id=difficulty_id).prefetch_related('sudokucell_set')
        for board in boards:
            cells = sorted(board.sudokucell_set.all(), key=lambda cell: cell.number)
            if [cell.number for cell in cells] != list(range(size * size)):
                continue
            if any(not 1 <= cell.value <= size for cell in cells):
                continue
            solution = [[cells[r * size + c].value for c in range(size)] for r in range(size)]
            if count_solutions(solution) != 1:
                continue
            if not lower <= sum(cell.is_empty for cell in cells) <= upper:
                continue
            puzzle = [[0 if cells[r * size + c].is_empty else solution[r][c]
                       for c in range(size)] for r in range(size)]
            try:
                if count_solutions(puzzle, deadline=monotonic() + budget) == 1:
                    count += 1
            except GenerationBudgetExceeded:
                # Legacy data is not a proven valid task when verification times out.
                continue
        return count
