"""Redis/Channels worker without the website apps, URL checks or SQL database."""
from sudoku.settings import *  # noqa: F403


INSTALLED_APPS = ['sudoku_v2.apps.SudokuV2Config']
ROOT_URLCONF = None
DATABASES = {}

# Conservative limits for one shared Twitch account; no moderator exceptions.
TWITCH_BOT_ENABLED = True
TWITCH_MAX_CHANNELS = 100
TWITCH_JOIN_LIMIT = 20
TWITCH_AUTH_LIMIT = 20
