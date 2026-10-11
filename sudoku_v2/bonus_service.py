"""Shared, server-only bonus application for cells and external adapters."""
from random import Random
from time import time

from django.conf import settings
from common.redis import CommitGuard
from .bonuses import BonusRequest, apply_bonus, normalize_bonus_params
from .storage import SudokuV2Storage


class BonusService:
    def __init__(self, storage: SudokuV2Storage, rng: Random | None = None):
        self.storage = storage
        self.rng = rng or Random()

    async def collect_targets(self, lobby, owner_name, target_names):
        boards, expected = {}, {}
        names = await self.storage.get_active_usernames(lobby)
        for name in sorted(names - {owner_name}):
            if '*' not in target_names and name not in target_names:
                continue
            board = await self.storage.get_board_state(lobby, name)
            lease = await self.storage.get_presence_token(lobby, name)
            if not board or not lease:
                continue
            public = board['public']
            if not public['generationId'] or public['requiresGeneration'] or public['completed']:
                continue
            boards[name] = board
            expected[name] = (public['generationId'], public['revision'], lease)
        return boards, expected

    def prepare(self, boards, request, event_id, now_ms, source):
        params = normalize_bonus_params(request.kind, request.params,
                                        [b['public']['size'] for b in boards.values()], self.rng)
        duration = getattr(settings, 'SUDOKU_V2_EFFECT_DURATION_MS', 30000)
        updated = {name: apply_bonus(board, request.kind, params, effect_id=event_id,
                                    now_ms=now_ms, duration_ms=duration)
                   for name, board in boards.items()}
        event = {'eventId': event_id, 'source': source, 'kind': request.kind, 'params': params,
                 'targets': [b['public'] for b in updated.values()], 'serverNow': now_ms}
        return updated, event

    async def apply_external(self, lobby, owner_name, request, *, event_id, guards, strings,
                             source_type='twitch_chat'):
        for _ in range(8):
            if not await self.storage.redis.guards_match(guards):
                return None
            owner_lease = await self.storage.get_presence_token(lobby, owner_name)
            if not owner_lease:
                return None
            boards, expected = await self.collect_targets(lobby, owner_name, request.target_names)
            if not boards:
                return None
            updated, event = self.prepare(boards, request, event_id, int(time()*1000),
                                          {'type': source_type, 'name': owner_name})
            result = await self.storage.commit_boards(lobby, updated, expected,
                guards=[*guards, CommitGuard(self.storage._presence_key(lobby, owner_name), 'string', owner_lease)],
                strings=strings)
            if result == 'saved':
                return event
        return None
