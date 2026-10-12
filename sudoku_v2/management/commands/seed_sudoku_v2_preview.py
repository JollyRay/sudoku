from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pathlib import Path
import json
from game.models import Difficulty, SudokuBoard, SudokuCell


class Command(BaseCommand):
    help = 'Create deterministic puzzles in the explicitly isolated browser preview only.'

    def handle(self, *args, **options):
        if not getattr(settings, 'SUDOKU_V2_PREVIEW', False) or not getattr(settings, 'SUDOKU_V2_PREFIX', '').startswith('preview-sudoku-v2:'):
            raise CommandError('Use isolated preview settings with an explicit namespace')
        fixtures = json.loads((Path(__file__).resolve().parents[2] / 'fixtures' / 'preview_puzzles.json').read_text(encoding='utf-8'))
        with transaction.atomic():
            for data in fixtures:
                difficulty, _ = Difficulty.objects.get_or_create(name=data['difficulty'], defaults={
                    'top_limit': {'easy': 30, 'medium': 55, 'hard': 81}[data['difficulty']],
                })
                if SudokuBoard.objects.for_size(data['size']).filter(difficulty=difficulty).exists():
                    continue
                board = SudokuBoard.objects.create(difficulty=difficulty)
                empty = set(data['empty'])
                SudokuCell.objects.bulk_create([
                    SudokuCell(board=board, number=i, value=value, is_empty=i in empty)
                    for i, value in enumerate(data['solution'])
                ])
        self.stdout.write('Fixed preview puzzles ready: 9x9 and 16x16, three difficulties')
