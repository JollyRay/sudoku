"""Exercise process settings without importing unrelated apps or touching SQL."""
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


STARTUP_CHECK = """
import importlib
import os
import sys
from unittest.mock import patch

import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False

profile, command, *unavailable_apps = sys.argv[1:]
for module in unavailable_apps:
    sys.modules[module] = None

base = importlib.import_module('sudoku.settings')
config = importlib.import_module(profile)
assert config.CHANNEL_LAYERS == base.CHANNEL_LAYERS
if command == 'fillSudoku':
    assert config.DATABASES == base.DATABASES
    config.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
else:
    assert not config.DATABASES, 'The Twitch worker must not use SQL'
config.SECRET_KEY = 'process-settings-test-only'
os.environ['DJANGO_SETTINGS_MODULE'] = profile

import django
from django.core.management import call_command, get_commands, load_command_class
from django.db.backends.base.base import BaseDatabaseWrapper

with patch.object(BaseDatabaseWrapper, 'cursor', side_effect=AssertionError('Startup accessed SQL')):
    django.setup()
    call_command('check')
    commands = get_commands()
    load_command_class(commands[command], command)
    other_command = 'fillSudoku' if command == 'run_twitch_bot' else 'run_twitch_bot'
    assert other_command not in commands
"""


class ProcessSettingsTests(SimpleTestCase):
    def check_startup(self, profile: str, command: str, unavailable_apps: list[str]) -> None:
        result = subprocess.run(
            [sys.executable, '-c', STARTUP_CHECK, profile, command, *unavailable_apps],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_worker_starts_without_other_apps_or_sql(self):
        self.check_startup(
            'sudoku_v2.worker_settings', 'run_twitch_bot',
            ['game', 'voice', 'bunker', 'breach_protocol', 'tests'],
        )

    def test_generator_starts_without_legacy_hooks_or_other_apps(self):
        self.check_startup(
            'sudoku_v2.generator_settings', 'fillSudoku',
            ['game.apps', 'voice', 'bunker', 'breach_protocol', 'sudoku_v2.apps', 'tests'],
        )
