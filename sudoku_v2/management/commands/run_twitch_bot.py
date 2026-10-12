import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from sudoku_v2.storage import SudokuV2Storage
from sudoku_v2.twitch.registry import TwitchRegistry
from sudoku_v2.twitch.service import TwitchService
from sudoku_v2.twitch.worker import run_twitch_worker


class Command(BaseCommand):
    help='Run the shared read-only Twitch chat bot (use sudoku_v2.worker_settings)'

    def handle(self,*args,**options):
        if not getattr(settings,'TWITCH_BOT_ENABLED',True): raise CommandError('Twitch worker disabled')
        if any(app in settings.INSTALLED_APPS for app in ('game.apps.GameConfig','voice.apps.VoiceConfig')):
            raise CommandError('Use --settings=sudoku_v2.worker_settings to avoid legacy startup hooks')
        async def run():
            storage=SudokuV2Storage()
            registry=TwitchRegistry(storage)
            try:
                return await run_twitch_worker(registry,TwitchService(registry,bot_id=''),stop_event=asyncio.Event())
            finally: await storage.redis.close()
        try:
            status = asyncio.run(run())
            if status == 'auth_error':
                raise CommandError('Twitch authentication failed; check bot login, OAuth token and chat:read scope')
            if status == 'error':
                raise CommandError('Twitch worker unavailable; check Redis and network')
        except KeyboardInterrupt: pass
        except ValueError as error: raise CommandError(str(error)) from None
