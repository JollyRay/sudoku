"""Isolated test/demo settings; never run the old game's startup cleanup."""
from django.apps import AppConfig

from sudoku.settings import *  # noqa: F403


class TestGameConfig(AppConfig):
    name = "game"
    default_auto_field = "django.db.models.BigAutoField"


class TestVoiceConfig(AppConfig):
    name = "voice"
    default_auto_field = "django.db.models.BigAutoField"


_TEST_APP_CONFIGS = {
    "game.apps.GameConfig": "sudoku_v2.test_settings.TestGameConfig",
    "voice.apps.VoiceConfig": "sudoku_v2.test_settings.TestVoiceConfig",
}
INSTALLED_APPS = [
    _TEST_APP_CONFIGS.get(app, app)
    for app in INSTALLED_APPS  # noqa: F405
]
SECRET_KEY = "sudoku-v2-local-tests-only"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN = CSRF_COOKIE_DOMAIN = None
COOKIE_SECURE = SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
