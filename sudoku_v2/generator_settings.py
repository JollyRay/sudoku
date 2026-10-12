"""Puzzle generation against the project database, without legacy startup cleanup."""
from django.apps import AppConfig

from sudoku.settings import *  # noqa: F403


class GeneratorGameConfig(AppConfig):
    # The puzzle models still live in game; its destructive ready() is not needed.
    name = 'game'
    default_auto_field = 'django.db.models.BigAutoField'


INSTALLED_APPS = ['sudoku_v2.generator_settings.GeneratorGameConfig']
ROOT_URLCONF = None
TWITCH_BOT_ENABLED = False
