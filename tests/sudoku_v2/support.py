"""Shared fixtures; mixins contain no test cases and do not inherit TestCase."""
import asyncio
import os
from random import Random
from unittest.mock import AsyncMock
from uuid import uuid4

from django.test import override_settings
from redis.asyncio import Redis

from common.redis import RedisClient
from game.generator import generate_solution
from sudoku_v2.storage import SudokuV2Storage, empty_board
from sudoku_v2.twitch.registry import TwitchRegistry
from sudoku_v2.twitch.service import TwitchService
from sudoku_v2.twitch.types import ExternalBonusCommand


CATALOG = {"difficulties": [{"value": "medium", "label": "Средняя"}],
           "sizes": [9], "bonuses": [],
           "symbolPresets": [{"id": "plain", "label": "Цифры", "imageUrl": None}]}


def make_stored_board():
    solution = {str(r * 9 + c): (r * 3 + r // 3 + c) % 9 + 1
                for r in range(9) for c in range(9)}
    return {"public": {
        "name": "Иван", "generationId": "A", "revision": 1, "size": 9,
        "difficulty": "medium", "values": dict(solution),
        "fixedCells": list(range(2, 81)), "bonuses": {"0": "ROLL"},
        "wrongCells": [], "startedAt": 1000, "finishedAt": None,
        "completed": False, "requiresGeneration": False,
        "rowOrder": list(range(9)), "columnOrder": list(range(9)),
        "consumedBonusCells": [], "activeEffects": [],
    }, "solution": solution}


def sized_board(size, name='Иван'):
    solution = {str(r*size+c): v for r, row in enumerate(generate_solution(size, Random(42))) for c, v in enumerate(row)}
    public = empty_board(name, size)
    public.update(generationId='A', revision=1, values={**solution, '0': '', '1': ''},
                  fixedCells=list(range(2, size*size)), startedAt=1000)
    return {'public': public, 'solution': solution}


class RedisFixture:
    async def asyncSetUp(self):
        self.raw = Redis.from_url(os.environ["SUDOKU_V2_TEST_REDIS_URL"], decode_responses=True)
        client = object.__new__(RedisClient)
        client._redis_client = self.raw
        self.storage = SudokuV2Storage(client)
        self.lobby = "test-ui-" + uuid4().hex
        self.name = "Иван"
        await self.storage.acquire_presence(self.lobby, self.name, "lease")

    async def asyncTearDown(self):
        keys = [key async for key in self.raw.scan_iter(self.storage._lobby_prefix(self.lobby) + ":*")]
        if keys:
            await self.raw.delete(*keys)
        await self.raw.aclose()


class BonusFixture(RedisFixture):
    async def add_board(self, name, size=9, completed=False):
        lease = 'lease' if name == self.name else name + '-lease'
        if name != self.name:
            await self.storage.acquire_presence(self.lobby, name, lease)
        board = sized_board(size, name)
        board['public'].update(values={}, fixedCells=[], completed=completed, bonuses={'0': 'SHADOW_BOX'})
        await self.storage.save_board_state(self.lobby, name, board, None, lease)
        return board


class TwitchFixture(BonusFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.settings = override_settings(SUDOKU_V2_PREFIX='test-' + self.lobby)
        self.settings.enable()
        # The setup presence preceded the namespace override.
        await self.storage.acquire_presence(self.lobby, self.name, 'lease')
        self.registry = TwitchRegistry(self.storage)
        self.publish = AsyncMock()
        self.service = TwitchService(self.registry, bot_id='bot', publish=self.publish)
        await self.add_board(self.name)
        await self.add_board('Лена')
        self.binding = await self.registry.register(self.lobby, self.name, 'lease', 'Channel', 0)

    async def asyncTearDown(self):
        keys = [key async for key in self.raw.scan_iter('test-' + self.lobby + '*')]
        if keys:
            await self.raw.delete(*keys)
        self.settings.disable()
        await super().asyncTearDown()

    def command(self, message_id='one', text='!blur', sent_at=None):
        return ExternalBonusCommand(
            'twitch_chat', message_id, 'channel', 'viewer',
            sent_at or self.binding['registeredAt'], text,
        )


class FakeWriter:
    def __init__(self):
        self.lines = []
        self.closed = False

    def write(self, data):
        self.lines.append(data.decode())

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


async def eventually(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(.005)
    raise AssertionError('Condition not reached')
