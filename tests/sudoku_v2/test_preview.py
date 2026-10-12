from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from io import StringIO
from unittest.mock import patch
import importlib
import os
from django.conf import settings
from game.models import SudokuBoard
from game.generator import count_solutions


class PreviewSafetyTests(SimpleTestCase):
    def test_cross_process_preview_channel_layer_is_isolated(self):
        prefix='preview-sudoku-v2:'+'b'*32
        with patch.dict(os.environ, {'SUDOKU_V2_PREVIEW_DB':str(settings.BASE_DIR/'.tmp/sudoku-v2-preview-test.sqlite3'),
                                     'SUDOKU_V2_PREVIEW_PREFIX':prefix,'SUDOKU_V2_PREVIEW_REDIS_URL':'redis://127.0.0.1:6379/15'}):
            module=importlib.import_module('tests.preview_settings')
            layer=module.CHANNEL_LAYERS['default']
            self.assertEqual(layer['BACKEND'],'channels_redis.core.RedisChannelLayer')
            self.assertEqual(layer['CONFIG']['prefix'],prefix+'-channels')
            self.assertEqual(layer['CONFIG']['hosts'],['redis://127.0.0.1:6379/15'])

    def test_seed_refuses_non_preview_settings(self):
        with self.assertRaisesMessage(CommandError, 'isolated preview'):
            call_command('seed_sudoku_v2_preview')


@override_settings(SUDOKU_V2_PREVIEW=True, SUDOKU_V2_PREFIX='preview-sudoku-v2:'+'a'*32)
class PreviewSeedTests(TestCase):
    def test_fixed_seed_is_unique_idempotent_and_does_not_generate(self):
        with patch('game.management.commands.fillSudoku.generate_puzzle', side_effect=AssertionError('No runtime generation')):
            call_command('seed_sudoku_v2_preview', stdout=StringIO())
            call_command('seed_sudoku_v2_preview', stdout=StringIO())
        self.assertEqual(SudokuBoard.objects.count(), 6)
        for board in SudokuBoard.objects.all():
            cells = list(board.sudokucell_set.order_by('number'))
            size = int(len(cells)**.5)
            puzzle = [[0 if cells[r*size+c].is_empty else cells[r*size+c].value for c in range(size)] for r in range(size)]
            self.assertEqual(count_solutions(puzzle), 1)
