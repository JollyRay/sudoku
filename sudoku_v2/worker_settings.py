"""Production DB/channel settings without destructive legacy AppConfig.ready hooks."""
from django.apps import AppConfig

from sudoku.settings import *  # noqa: F403


class WorkerGameConfig(AppConfig):
    name = 'game'
    default_auto_field = 'django.db.models.BigAutoField'


class WorkerVoiceConfig(AppConfig):
    name = 'voice'
    default_auto_field = 'django.db.models.BigAutoField'


_WORKER_APPS = {
    'game.apps.GameConfig': 'sudoku_v2.worker_settings.WorkerGameConfig',
    'voice.apps.VoiceConfig': 'sudoku_v2.worker_settings.WorkerVoiceConfig',
}
INSTALLED_APPS = [_WORKER_APPS.get(app, app) for app in INSTALLED_APPS]  # noqa: F405

# Conservative limits for one shared Twitch account; no moderator exceptions.
TWITCH_BOT_ENABLED = True
TWITCH_MAX_CHANNELS = 100
TWITCH_JOIN_LIMIT = 20
TWITCH_AUTH_LIMIT = 20
