import json
import asyncio
from collections import defaultdict
from time import time
from uuid import uuid4

from common.redis import CommitGuard, ExpiringValue
from ..bonus_service import BonusService
from ..bonuses import BonusRequest
from ..broadcast import publish_bonus
from .commands import normalize_channel, parse_command


class TwitchService:
    def __init__(self, registry, *, bot_id, publish=publish_bonus):
        self.registry, self.storage = registry, registry.storage
        self.bot_id, self.publish = bot_id, publish
        self.bonuses = BonusService(self.storage)
        self._channel_locks = defaultdict(asyncio.Lock)

    async def handle(self, command, *, guards=()):
        if (command.source != 'twitch_chat' or not command.message_id or command.sender_id == self.bot_id
                or type(command.sent_at_ms) is not int):
            return None
        parsed = parse_command(command.text)
        if not parsed:
            return None
        try:
            channel = normalize_channel(command.channel)
        except ValueError:
            return None
        # The shared bot processes one channel in order; CAS also fences other processes.
        async with self._channel_locks[channel]:
            return await self._apply(command, parsed, channel, guards)

    async def _apply(self, command, parsed, channel, guards):
        registry = self.registry
        key = registry.binding_key(channel)
        dedup = registry.dedup_key(self.bot_id, channel, command.message_id)
        binding_id = None
        for _ in range(32):
            if await self.storage.redis.get(dedup):
                return None
            binding = await registry.get(channel)
            if not binding or command.sent_at_ms < binding['registeredAt']:
                return None
            if binding_id is not None and binding['bindingId'] != binding_id:
                return None
            binding_id = binding['bindingId']
            lobby, owner = binding['lobby'], binding['owner']
            if await self.storage.get_room_epoch(lobby) != binding['roomEpoch']:
                await registry._prune(channel)
                return None
            now = int(time() * 1000)
            last = binding['lastAppliedAt']
            if last is not None and now - last < binding['cooldownSeconds'] * 1000:
                return None
            targets, _ = await self.bonuses.collect_targets(lobby, owner, ['*'])
            if not targets or not await self.storage.get_presence_token(lobby, owner):
                return None
            names = [parsed.name] if parsed.name in targets else ['*']
            checks = [
                *guards,
                CommitGuard(key, 'hash', registry.encode(binding)),
                CommitGuard(self.storage._lobby_prefix(lobby) + ':epoch', 'string', binding['roomEpoch']),
                CommitGuard(dedup, 'string', None),
            ]
            event = await self.bonuses.apply_external(lobby, owner, BonusRequest(parsed.kind, names, parsed.raw_params),
                event_id=uuid4().hex, guards=checks, strings={dedup: ExpiringValue('1', 86400)},
                hash_updates=lambda applied_at: {key: {'lastAppliedAt': json.dumps(applied_at)}})
            if event:
                await self.publish(lobby, event)
                return event
            # The next attempt reloads binding/CD/targets; old guards are never reused.
            if not await self.storage.redis.guards_match(guards):
                return None
        return None
