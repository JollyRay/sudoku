"""Explicitly isolated local browser preview. Refuses ambiguous paths/namespaces."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured
from .test_settings import *  # noqa: F403

_database = Path(os.environ.get('SUDOKU_V2_PREVIEW_DB', '')).resolve()
_scratch = (BASE_DIR / '.tmp').resolve()  # noqa: F405
SUDOKU_V2_PREFIX = os.environ.get('SUDOKU_V2_PREVIEW_PREFIX', '')
SUDOKU_V2_REDIS_URL = os.environ.get('SUDOKU_V2_PREVIEW_REDIS_URL', '')
_redis = urlparse(SUDOKU_V2_REDIS_URL)
if (_database.parent != _scratch or not _database.name.startswith('sudoku-v2-preview')
        or _database.suffix != '.sqlite3'
        or not re.fullmatch(r'preview-sudoku-v2:[a-f0-9]{32}', SUDOKU_V2_PREFIX)
        or _redis.scheme != 'redis' or _redis.hostname not in ('localhost', '127.0.0.1', '::1')
        or _redis.path != '/15'):
    raise ImproperlyConfigured('Explicit isolated preview DB, Redis DB15 and UUID namespace required')
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(_database)}}
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer',
    'CONFIG': {'hosts': [SUDOKU_V2_REDIS_URL], 'prefix': SUDOKU_V2_PREFIX+'-channels'}}}
SUDOKU_V2_PREVIEW = True
TWITCH_BOT_ENABLED = False
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
