import asyncio
import os
from copy import deepcopy
from math import isqrt
from random import Random
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch
from django.test import SimpleTestCase, override_settings
from channels.testing import WebsocketCommunicator
from common.redis import CommitGuard, ExpiringValue
from sudoku_v2.consumers import SudokuV2Consumer

from sudoku_v2.bonus_rules import BonusRequest, apply_bonus, normalize_bonus_params
from sudoku_v2.bonus_service import BonusService
from sudoku_v2.broadcast import publish_bonus
from sudoku_v2.service import SudokuV2Service, SudokuV2Error
from .support import BonusFixture, sized_board


class BonusTests(SimpleTestCase):
    def test_shared_params_mixed_sizes(self):
        rng = Random(42)
        for _ in range(30):
            params = normalize_bonus_params('SWAP', {'first': 0, 'second': 8}, [9, 16], rng)
            for size in (9, 16):
                self.assertEqual(params['first']//isqrt(size), params['second']//isqrt(size))
                before = sized_board(size)
                after = apply_bonus(before, 'SWAP', params, effect_id='swap', now_ms=1000, duration_ms=30000)
                self.assertEqual(before['solution'], after['solution'])
                self.assertEqual(before['public']['values'], after['public']['values'])
                order = after['public']['rowOrder' if params['axis']=='row' else 'columnOrder']
                self.assertEqual(order[params['first']], params['second'])
        params = normalize_bonus_params('ROLL', {'box': 15}, [9, 16], rng)
        self.assertLess(params['box'], 9)

    def test_instances_and_duration(self):
        before = sized_board(16)
        first = apply_bonus(before, 'SHADOW_BOX', {'box': 0}, effect_id='A', now_ms=1000, duration_ms=30000)
        second = apply_bonus(first, 'SHADOW_BOX', {'box': 0}, effect_id='B', now_ms=2000, duration_ms=30000)
        self.assertEqual([e['id'] for e in second['public']['activeEffects']], ['A', 'B'])
        self.assertEqual([e['expiresAt'] for e in second['public']['activeEffects']], [31000, 32000])
        self.assertEqual(second['solution'], before['solution'])


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'), 'Set an isolated test Redis URL')
class BonusStorageTests(BonusFixture, IsolatedAsyncioTestCase):
    async def move(self, value):
        return await SudokuV2Service(self.lobby, self.name, self.storage, 'lease').set_value({
            'boardName': self.name, 'generationId': 'A', 'cellIndex': 0, 'value': value,
        })

    async def test_first_correct_consumes_once(self):
        board = await self.add_board(self.name)
        await self.add_board('Лена')
        correct = board['solution']['0']
        result = await self.move(correct%9+1)
        self.assertEqual(result['board']['consumedBonusCells'], [])
        first = await self.move(correct)
        self.assertEqual(first['board']['consumedBonusCells'], [0])
        self.assertIn('_bonus_event', first)
        await self.move('')
        second = await self.move(correct)
        self.assertNotIn('_bonus_event', second)
        target = await self.storage.get_board_state(self.lobby, 'Лена')
        self.assertEqual(len(target['public']['activeEffects']), 1)
        self.assertEqual((await self.storage.get_board_state(self.lobby, self.name))['public']['activeEffects'], [])

    async def test_solo_consumes_and_later_joiner_has_no_effect(self):
        board = await self.add_board(self.name)
        result = await self.move(board['solution']['0'])
        self.assertEqual(result['board']['consumedBonusCells'], [0])
        self.assertNotIn('_bonus_event', result)
        await self.add_board('Лена')
        await self.move('')
        await self.move(board['solution']['0'])
        self.assertEqual((await self.storage.get_board_state(self.lobby, 'Лена'))['public']['activeEffects'], [])

    async def test_external_targets_present_unfinished_players_including_owner(self):
        await self.add_board(self.name)
        for name, size in [('Лена', 9), ('Макс', 16), ('Готово', 9), ('Ушёл', 9)]:
            await self.add_board(name, size, completed=name=='Готово')
        await self.storage.release_presence(self.lobby, 'Ушёл', 'Ушёл-lease')
        event = await BonusService(self.storage).apply_external(self.lobby, self.name, BonusRequest('ROLL', ['*'], {}), event_id='one', guards=[], strings={})
        self.assertEqual({b['name'] for b in event['targets']}, {self.name, 'Лена', 'Макс'})
        self.assertEqual(event['targets'][0]['activeEffects'][0]['params'], event['targets'][1]['activeEffects'][0]['params'])
        self.assertEqual(len((await self.storage.get_board_state(self.lobby, self.name))['public']['activeEffects']), 1)

    async def test_concurrent_correct_moves_emit_one_bonus(self):
        board = await self.add_board(self.name)
        await self.add_board('Лена')
        results = await asyncio.gather(self.move(board['solution']['0']), self.move(board['solution']['0']))
        self.assertEqual(sum('_bonus_event' in result for result in results), 1)
        self.assertEqual((await self.storage.get_board_state(self.lobby, self.name))['public']['consumedBonusCells'], [0])
        self.assertEqual(len((await self.storage.get_board_state(self.lobby, 'Лена'))['public']['activeEffects']), 1)

    async def test_target_generation_conflict_has_no_partial_write(self):
        source = await self.add_board(self.name)
        target = await self.add_board('Лена')
        new_target = deepcopy(target);new_target['public'].update(generationId='B', revision=2)
        await self.storage.save_board_state(self.lobby, 'Лена', new_target, ('A', 1), 'Лена-lease')
        changed = deepcopy(source);changed['public'].update(consumedBonusCells=[0], revision=2)
        result = await self.storage.commit_boards(self.lobby, {self.name: changed, 'Лена': target},
            {self.name: ('A', 1, 'lease'), 'Лена': ('A', 1, 'Лена-lease')})
        self.assertEqual(result, 'conflict')
        self.assertEqual(await self.storage.get_board_state(self.lobby, self.name), source)
        self.assertEqual(await self.storage.get_board_state(self.lobby, 'Лена'), new_target)

    async def test_replaced_source_lease_cannot_apply_bonus(self):
        board = await self.add_board(self.name)
        target = await self.add_board('Лена')
        await self.raw.set(self.storage._presence_key(self.lobby, self.name), 'replacement')
        with self.assertRaises(SudokuV2Error) as error:
            await self.move(board['solution']['0'])
        self.assertEqual(error.exception.code, 'connection_replaced')
        self.assertEqual(await self.storage.get_board_state(self.lobby, self.name), board)
        self.assertEqual(await self.storage.get_board_state(self.lobby, 'Лена'), target)

    async def test_commit_survives_failed_broadcast(self):
        board = await self.add_board(self.name)
        await self.add_board('Лена')
        result = await self.move(board['solution']['0'])
        layer = AsyncMock();layer.group_send.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            await publish_bonus(self.lobby, result['_bonus_event'], channel_layer=layer)
        self.assertEqual((await self.storage.get_board_state(self.lobby, self.name))['public']['consumedBonusCells'], [0])
        self.assertEqual(len((await self.storage.get_board_state(self.lobby, 'Лена'))['public']['activeEffects']), 1)

    @override_settings(SUDOKU_V2_EFFECT_DURATION_MS=45000)
    async def test_last_correct_cell_can_complete_and_trigger_configured_effect(self):
        board = await self.add_board(self.name)
        board['public']['values'] = {i: v for i, v in board['solution'].items() if i != '0'}
        await self.storage.save_board_state(self.lobby, self.name, board, ('A', 1), 'lease')
        await self.add_board('Лена')
        result = await self.move(board['solution']['0'])
        self.assertTrue(result['board']['completed'])
        effect = (await self.storage.get_board_state(self.lobby, 'Лена'))['public']['activeEffects'][0]
        self.assertEqual(effect['expiresAt'] - effect['startsAt'], 45000)

    async def test_external_requires_owner_presence_even_without_owner_board(self):
        target = await self.add_board('Лена')
        await self.storage.release_presence(self.lobby, self.name, 'lease')
        event = await BonusService(self.storage).apply_external(self.lobby, self.name,
            BonusRequest('ROLL', ['*'], {}), event_id='id', guards=[], strings={})
        self.assertIsNone(event)
        self.assertEqual(await self.storage.get_board_state(self.lobby, 'Лена'), target)

    async def test_room_epoch_changes_after_last_departure(self):
        first = await self.storage.get_room_epoch(self.lobby)
        self.assertTrue(first)
        await self.storage.acquire_presence(self.lobby, 'Лена', 'second')
        self.assertEqual(await self.storage.get_room_epoch(self.lobby), first)
        await self.storage.release_presence(self.lobby, 'Лена', 'second')
        await self.storage.release_presence(self.lobby, self.name, 'lease')
        await self.storage.acquire_presence(self.lobby, self.name, 'new')
        self.assertNotEqual(await self.storage.get_room_epoch(self.lobby), first)

    async def test_guards_and_expiring_strings_commit_with_boards(self):
        board = await self.add_board('Лена')
        key = self.storage._lobby_prefix(self.lobby) + ':guard'
        dedup = key + ':dedup'
        await self.raw.hset(key, mapping={'bindingId': 'new', 'extra': 'keep'})
        service = BonusService(self.storage)
        request = BonusRequest('ROLL', ['*'], {})
        guards = [CommitGuard(key, 'hash', {'bindingId': 'old'}), CommitGuard(dedup, 'string', None)]
        self.assertIsNone(await service.apply_external(self.lobby, self.name, request, event_id='id', guards=guards,
                                                       strings={dedup: ExpiringValue('seen', 86400)}))
        self.assertEqual(await self.storage.get_board_state(self.lobby, 'Лена'), board)
        self.assertIsNone(await self.raw.get(dedup))
        guards[0] = CommitGuard(key, 'hash', {'bindingId': 'new'})
        self.assertIsNotNone(await service.apply_external(self.lobby, self.name, request, event_id='id', guards=guards,
                                                          strings={dedup: ExpiringValue('seen', 86400)}))
        self.assertGreater(await self.raw.ttl(dedup), 86390)
        self.assertIsNone(await service.apply_external(self.lobby, self.name, request, event_id='id', guards=guards, strings={}))
        self.assertEqual(len((await self.storage.get_board_state(self.lobby, 'Лена'))['public']['activeEffects']), 1)

    async def test_expired_effects_pruned_maps_preserved(self):
        from time import time
        board = await self.add_board(self.name)
        now = int(time()*1000)
        board = apply_bonus(board, 'ROLL', {'box': 0}, effect_id='expired', now_ms=now-40000, duration_ms=30000)
        board = apply_bonus(board, 'ROLL', {'box': 1}, effect_id='live', now_ms=now, duration_ms=30000)
        board = apply_bonus(board, 'SWAP', {'axis': 'row', 'first': 0, 'second': 1}, effect_id='swap', now_ms=now, duration_ms=30000)
        # Simulate an older stored snapshot containing the expired instance too.
        board['public']['activeEffects'].append({'id': 'expired', 'kind': 'ROLL', 'params': {'box': 0}, 'startsAt': now-40000, 'expiresAt': now-10000})
        await self.storage.save_board_state(self.lobby, self.name, board, ('A', 1), 'lease')
        snapshot = (await self.storage.get_board_state(self.lobby, self.name))['public']
        self.assertEqual([e['id'] for e in snapshot['activeEffects']], ['live'])
        self.assertEqual(snapshot['rowOrder'][:2], [1, 0])

    async def test_websocket_ack_precedes_public_bonus_without_secrets(self):
        await self.storage.release_presence(self.lobby, self.name, 'lease')
        with patch('sudoku_v2.consumers.SudokuV2Storage', return_value=self.storage):
            clients = [WebsocketCommunicator(SudokuV2Consumer.as_asgi(), '/ws/sudoku-v2/') for _ in range(2)]
            for client, name in zip(clients, [self.name, 'Лена']):
                client.scope['session'] = {'sudoku_v2_room': self.lobby, 'sudoku_v2_username': name}
                self.assertTrue((await client.connect())[0])
            a, b = clients
            try:
                await a.receive_json_from()  # join snapshot
                for name in [self.name, 'Лена']:
                    board = sized_board(9, name)
                    board['public'].update(values={}, fixedCells=[], bonuses={'0': 'ROLL'})
                    lease = await self.storage.get_presence_token(self.lobby, name)
                    await self.storage.save_board_state(self.lobby, name, board, None, lease)
                    await self.storage.save_context(self.lobby, name, {'private': 'secret'}, lease)
                await a.send_json_to({'kind': 'set_value', 'data': {'boardName': self.name,
                    'generationId': 'A', 'cellIndex': 0, 'value': board['solution']['0']}})
                ack = await a.receive_json_from()
                self.assertEqual(ack['kind'], 'set_value')
                self.assertNotIn('_bonus_event', ack['data'])
                own_event, peer_event = await a.receive_json_from(), await b.receive_json_from()
                self.assertEqual(own_event, peer_event)
                self.assertEqual(own_event['kind'], 'bonus_applied')
                self.assertEqual({t['name'] for t in own_event['data']['targets']}, {self.name, 'Лена'})
                self.assertNotIn('solution', str(own_event))
                self.assertNotIn('secret', str(own_event))
            finally:
                await b.disconnect()
                await a.disconnect()
