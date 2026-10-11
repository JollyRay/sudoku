import asyncio
import os
from copy import deepcopy
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from redis.asyncio import Redis
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from common.redis import RedisClient
from .storage import SudokuV2Storage
from .test_gameplay import make_stored_board
from .test_gameplay import CATALOG
from .consumers import SudokuV2Consumer


@skipUnless(os.environ.get("SUDOKU_V2_TEST_REDIS_URL"), "Set an isolated test Redis URL")
class StorageIntegrationTests(IsolatedAsyncioTestCase):
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

    async def test_snapshot_conflicts_and_lease(self):
        board = make_stored_board()
        self.assertEqual(await self.storage.save_board_state(self.lobby, self.name, board, None, "lease"), "saved")
        self.assertEqual(await self.storage.get_board_state(self.lobby, self.name), board)
        candidates = [deepcopy(board), deepcopy(board)]
        candidates[0]["public"].update(generationId="B", revision=2, bonuses={"1": "SWAP"})
        candidates[1]["public"]["revision"] = 2
        candidates[1]["public"]["values"]["0"] = ""
        results = await asyncio.gather(*[
            self.storage.save_board_state(self.lobby, self.name, b, ("A", 1), "lease") for b in candidates
        ])
        self.assertEqual(sorted(results), ["conflict", "saved"])
        self.assertEqual(await self.storage.get_board_state(self.lobby, self.name), candidates[results.index("saved")])
        await self.raw.set(self.storage._presence_key(self.lobby, self.name), "replacement")
        before = await self.storage.get_board_state(self.lobby, self.name)
        self.assertEqual(await self.storage.save_board_state(self.lobby, self.name, board, None, "lease"), "replaced")
        self.assertEqual(await self.storage.get_board_state(self.lobby, self.name), before)
        self.assertFalse(await self.storage.save_context(self.lobby, self.name, {"username": self.name}, "lease"))

    async def test_legacy_requires_generation(self):
        # Existing data without metadata is still readable; its obsolete writer is gone.
        await self.raw.hset(self.storage._board_key(self.lobby, self.name), mapping={"0": "1"})
        await self.raw.hset(self.storage._fixed_cells_key(self.lobby, self.name), mapping={"0": "1"})
        board = await self.storage.get_board_state(self.lobby, self.name)
        self.assertTrue(board["public"]["requiresGeneration"])
        self.assertEqual(board["solution"], {})
        self.assertEqual(await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease"), "saved")
        self.assertFalse((await self.storage.get_board_state(self.lobby, self.name))["public"]["requiresGeneration"])

    async def test_last_departure_deletes_entire_room_only(self):
        await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease")
        await self.storage.save_context(self.lobby, self.name, {"username": self.name}, "lease")
        await self.storage.acquire_presence(self.lobby, "Лена", "second")
        self.assertTrue(await self.storage.release_presence(self.lobby, self.name, "lease"))
        self.assertIsNotNone(await self.storage.get_board_state(self.lobby, self.name))
        self.assertEqual(await self.storage.get_active_usernames(self.lobby), {"Лена"})
        prefix = self.storage._lobby_prefix(self.lobby)
        neighbor = prefix + "-neighbor:contexts"
        await self.raw.set(neighbor, "keep")
        try:
            self.assertTrue(await self.storage.release_presence(self.lobby, "Лена", "second"))
            self.assertEqual(await self.raw.keys(prefix + ":*"), [])
            self.assertEqual(await self.raw.get(neighbor), "keep")
        finally:
            await self.raw.delete(neighbor)

    async def test_stale_departure_cannot_delete_replacement(self):
        await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease")
        await self.raw.set(self.storage._presence_key(self.lobby, self.name), "new-lease")
        self.assertFalse(await self.storage.release_presence(self.lobby, self.name, "lease"))
        self.assertIsNotNone(await self.storage.get_board_state(self.lobby, self.name))
        self.assertTrue(await self.storage.renew_presence(self.lobby, self.name, "new-lease"))

    async def test_expired_last_lease_still_cleans_empty_room(self):
        await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease")
        await self.storage.save_context(self.lobby, self.name, {}, "lease")
        await self.raw.delete(self.storage._presence_key(self.lobby, self.name))
        self.assertFalse(await self.storage.release_presence(self.lobby, self.name, "lease"))
        self.assertEqual(await self.raw.keys(self.storage._lobby_prefix(self.lobby) + ":*"), [])

    async def test_expired_lease_preserves_room_with_another_player(self):
        await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease")
        await self.storage.acquire_presence(self.lobby, "Лена", "second")
        await self.raw.delete(self.storage._presence_key(self.lobby, self.name))
        self.assertFalse(await self.storage.release_presence(self.lobby, self.name, "lease"))
        self.assertIsNotNone(await self.storage.get_board_state(self.lobby, self.name))
        self.assertEqual(await self.storage.get_active_usernames(self.lobby), {"Лена"})

    async def test_join_racing_last_departure_keeps_new_presence(self):
        await asyncio.gather(
            self.storage.release_presence(self.lobby, self.name, "lease"),
            self.storage.acquire_presence(self.lobby, "Лена", "new-lease"),
        )
        self.assertEqual(await self.storage.get_active_usernames(self.lobby), {"Лена"})
        self.assertTrue(await self.storage.save_context(self.lobby, "Лена", {}, "new-lease"))

    async def test_new_room_does_not_reuse_abandoned_data(self):
        await self.storage.save_board_state(self.lobby, self.name, make_stored_board(), None, "lease")
        await self.raw.delete(self.storage._presence_key(self.lobby, self.name))
        self.assertTrue(await self.storage.acquire_presence(self.lobby, self.name, "new-lease"))
        self.assertIsNone(await self.storage.get_board_state(self.lobby, self.name))

    async def test_disconnect_broadcasts_remaining_participants(self):
        # Release the setup lease before connecting real consumers.
        await self.storage.release_presence(self.lobby, self.name, "lease")
        with override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}), patch(
            "sudoku_v2.consumers.SudokuV2Storage", return_value=self.storage
        ), patch("sudoku_v2.service.SudokuV2Service.get_catalog", AsyncMock(return_value=CATALOG)):
            a = WebsocketCommunicator(SudokuV2Consumer.as_asgi(), "/ws/sudoku-v2/")
            b = WebsocketCommunicator(SudokuV2Consumer.as_asgi(), "/ws/sudoku-v2/")
            a.scope["session"] = {"sudoku_v2_room": self.lobby, "sudoku_v2_username": self.name}
            b.scope["session"] = {"sudoku_v2_room": self.lobby, "sudoku_v2_username": "Лена"}
            self.assertTrue((await a.connect())[0])
            self.assertTrue((await b.connect())[0])
            joined = await a.receive_json_from()
            self.assertEqual(joined["kind"], "participants_data")
            self.assertEqual({board["name"] for board in joined["data"]["boards"]}, {self.name, "Лена"})
            await b.disconnect()
            departed = await a.receive_json_from()
            self.assertEqual([board["name"] for board in departed["data"]["boards"]], [self.name])
            await a.disconnect()
            self.assertEqual(await self.raw.keys(self.storage._lobby_prefix(self.lobby) + ":*"), [])
