from copy import deepcopy
from functools import lru_cache
from io import StringIO
from math import isqrt
import random
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from game import generator
from game.models import Difficulty, SudokuBoard, SudokuCell


class GeneratorTests(SimpleTestCase):
    def test_solution_constraints_9_and_16(self):
        for size in (9, 16):
            with self.subTest(size=size):
                board = generator.generate_solution(size, random.Random(42))
                wanted, base = set(range(1, size + 1)), isqrt(size)
                self.assertTrue(all(set(row) == wanted for row in board))
                self.assertTrue(all(set(col) == wanted for col in zip(*board)))
                for row in range(0, size, base):
                    for col in range(0, size, base):
                        self.assertEqual({board[r][c] for r in range(row, row + base)
                                          for c in range(col, col + base)}, wanted)
                self.assertEqual(board, generator.generate_solution(size, random.Random(42)))

    def test_puzzle_unique_and_matches_solution(self):
        for size in (9, 16):
            puzzle = generator.generate_puzzle(size, 8, 12, random.Random(12))
            self.assertEqual(puzzle.size, size)
            empty = sum(value == 0 for row in puzzle.puzzle for value in row)
            self.assertGreaterEqual(empty, 8)
            self.assertLessEqual(empty, 12)
            self.assertEqual(generator.count_solutions(puzzle.puzzle), 1)
            for r in range(size):
                for c in range(size):
                    self.assertIn(puzzle.puzzle[r][c], (0, puzzle.solution[r][c]))

    def test_solver_distinguishes_complete_invalid_and_multiple_without_mutation(self):
        solved = [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]]
        self.assertEqual(generator.count_solutions(solved), 1)
        invalid = deepcopy(solved)
        invalid[0][1] = 1
        self.assertEqual(generator.count_solutions(invalid), 0)
        empty = [[0] * 4 for _ in range(4)]
        self.assertEqual(generator.count_solutions(empty), 2)
        self.assertEqual(empty, [[0] * 4 for _ in range(4)])

    def test_generation_budget_never_accepts_unknown_uniqueness(self):
        with self.assertRaises(generator.GenerationBudgetExceeded):
            generator.count_solutions([[0] * 9 for _ in range(9)], node_budget=0)
        with patch.object(generator, 'count_solutions', side_effect=generator.GenerationBudgetExceeded):
            with self.assertRaises(generator.GenerationBudgetExceeded):
                generator.generate_puzzle(16, 1, 2, random.Random(0), max_attempts=1)

    def test_invalid_shape_values_and_generation_limits(self):
        for value in (0, 10, True):
            with self.assertRaises(ValueError):
                generator.generate_solution(value, random.Random(0))
        for puzzle in ([[1]], [[0] * 4] * 3, [[True] * 4] * 4, [[5] * 4] * 4):
            with self.assertRaises(ValueError):
                generator.count_solutions(puzzle)
        with self.assertRaises(ValueError):
            generator.generate_puzzle(9, 60, 50, random.Random(0))


@lru_cache(maxsize=6)
def quota_fixture(size, min_empty):
    return generator.generate_puzzle(size, min_empty, min_empty, random.Random(42))


def fixture_puzzle(size, min_empty, max_empty, rng, **kwargs):
    # Reuse proven fixtures; the CLI's quota tests do not rerun random generation.
    return deepcopy(quota_fixture(size, min_empty))


class FillSudokuTests(TestCase):
    def fill(self, **kwargs):
        call_command('fillSudoku', sizes=[9, 16], minimum=1, seed=42,
                     max_seconds=30, stdout=StringIO(), **kwargs)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=fixture_puzzle)
    def test_fill_counts_each_size_and_is_idempotent(self, generate):
        self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 6)
        for size in (9, 16):
            self.assertEqual(SudokuBoard.objects.for_size(size).count(), 3)
        self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 6)
        self.assertEqual(generate.call_count, 6)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=fixture_puzzle)
    def test_fill_rolls_back_cells_failure(self, generate):
        with patch.object(SudokuCell.objects, 'bulk_create', side_effect=RuntimeError('write failed')):
            with self.assertRaises(RuntimeError):
                self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 0)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=fixture_puzzle)
    def test_legacy_game_selects_only_9(self, generate):
        self.fill()
        for _ in range(6):
            cells = SudokuBoard.objects.random_for_user('room', 'name', 'easy')
            self.assertEqual(cells.count(), 81)
            self.assertEqual(SudokuBoard.objects.random().count(), 81)
        self.assertEqual(SudokuBoard.objects.random(size=16).count(), 256)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=fixture_puzzle)
    def test_corrupt_existing_board_does_not_fill_quota(self, generate):
        self.fill()
        board = SudokuBoard.objects.for_size(16).filter(difficulty__name='easy').get()
        SudokuCell.objects.filter(board=board, number=255).update(number=300)
        self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 7)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=fixture_puzzle)
    def test_nonunique_or_wrong_difficulty_does_not_fill_quota(self, generate):
        self.fill()
        board = SudokuBoard.objects.for_size(9).filter(difficulty__name='hard').get()
        SudokuCell.objects.filter(board=board).update(is_empty=True)
        self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 7)
        board = SudokuBoard.objects.for_size(16).filter(difficulty__name='easy').get()
        SudokuCell.objects.filter(board=board).update(is_empty=False)
        self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 8)

    @patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=generator.GenerationBudgetExceeded)
    def test_budget_error_reports_size_and_difficulty(self, generate):
        with self.assertRaisesMessage(CommandError, '9'):
            self.fill()
        self.assertEqual(SudokuBoard.objects.count(), 0)

    def test_invalid_cli_options(self):
        with self.assertRaises(CommandError):
            call_command('fillSudoku', sizes=[10], minimum=1, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('fillSudoku', sizes=[16], minimum=-1, stdout=StringIO())
