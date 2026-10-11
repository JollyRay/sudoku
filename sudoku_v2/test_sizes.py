import os
from random import Random
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch

from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from game.generator import generate_solution
from game.models import Difficulty, SudokuBoard, SudokuCell
from .constants import allowed_values
from .user_context import normalize_context, valid_board_value, valid_cell_index
from .service import SudokuV2Service, SudokuV2Error
from .storage import empty_board
from . import test_storage
from .test_gameplay import CATALOG
from .consumers import SudokuV2Consumer


def sized_board(size, name='Иван'):
    solution = {str(r*size+c): v for r, row in enumerate(generate_solution(size, Random(42))) for c, v in enumerate(row)}
    public = empty_board(name, size)
    public.update(generationId='A', revision=1, values={**solution, '0': '', '1': ''},
                  fixedCells=list(range(2, size*size)), startedAt=1000)
    return {'public': public, 'solution': solution}


class SizeTests(SimpleTestCase):
    def test_16_limits(self):
        self.assertEqual(allowed_values(16), ['', *range(1, 17)])
        self.assertTrue(valid_board_value(16, 16))
        for value in (17, True, 0, '16'):
            self.assertFalse(valid_board_value(value, 16))
        self.assertFalse(valid_board_value(16, 9))
        self.assertTrue(valid_cell_index(255, 16))
        for index in (256, True, -1):
            self.assertFalse(valid_cell_index(index, 16))
        board = sized_board(16)
        board['public']['fixedCells'] = []
        board['public']['values'] = {str(i): 16 if i < 16 else '' for i in range(256)}
        with self.assertRaises(SudokuV2Error) as error:
            SudokuV2Service.apply_value(board, 16, 16, 3000)
        self.assertEqual(error.exception.code, 'digit_limit_reached')
        board = sized_board(16)
        for i in (0, 1):
            board = SudokuV2Service.apply_value(board, i, board['solution'][str(i)], 4000)
        self.assertTrue(board['public']['completed'])
        self.assertEqual(board['public']['finishedAt'], 4000)

    def test_size_selection_does_not_change_active_board(self):
        config = normalize_context({'preferences': {'size': 16}}, 'Иван', CATALOG, board_size=9)
        self.assertEqual(config['preferences']['size'], 16)
        self.assertNotIn(10, config['allowedValues'])
        subset = normalize_context({'allowedValues': ['', 1, 16]}, 'Иван', CATALOG, board_size=16)
        self.assertEqual(subset['allowedValues'], ['', 1, 16])


class DatabaseSizeTests(TransactionTestCase):
    async def test_generation_filters_size_before_random(self):
        difficulty = await Difficulty.objects.acreate(name='medium', top_limit=55)
        for size in (9, 16):
            board = await SudokuBoard.objects.acreate(difficulty=difficulty)
            await SudokuCell.objects.abulk_create([
                SudokuCell(board=board, number=int(i), value=v, is_empty=int(i)<2)
                for i, v in sized_board(size)['solution'].items()
            ])
        for size in (16, 9, 16):
            board = await SudokuV2Service.get_random_board('medium', size)
            self.assertEqual(board['public']['size'], size)
            self.assertEqual(len(board['solution']), size*size)
        target = await SudokuBoard.objects.for_size(16).afirst()
        await SudokuCell.objects.filter(board=target, number=255).aupdate(number=300)
        self.assertIsNone(await SudokuV2Service.get_random_board('medium', 16))


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'), 'Set an isolated test Redis URL')
class SizeStorageTests(IsolatedAsyncioTestCase):
    asyncSetUp = test_storage.StorageIntegrationTests.asyncSetUp
    asyncTearDown = test_storage.StorageIntegrationTests.asyncTearDown

    async def test_16_moves_validate_active_size_and_subset(self):
        board = sized_board(16)
        board['public'].update(values={}, fixedCells=[0])
        await self.storage.save_board_state(self.lobby, self.name, board, None, 'lease')
        await self.storage.save_context(self.lobby, self.name, {'allowedValues': ['', 16]}, 'lease')
        service = SudokuV2Service(self.lobby, self.name, self.storage, 'lease')
        move = {'boardName': self.name, 'generationId': 'A', 'cellIndex': 255, 'value': 16}
        result = await service.set_value(move)
        self.assertEqual(result['board']['values']['255'], 16)
        for change in ({'cellIndex': 256}, {'value': 17}, {'value': True}, {'value': 1}, {'cellIndex': True}):
            with self.assertRaises(SudokuV2Error) as error:
                await service.set_value({**move, **change})
            self.assertEqual(error.exception.code, 'invalid_value')
        with self.assertRaises(SudokuV2Error) as error:
            await service.set_value({**move, 'cellIndex': 0})
        self.assertEqual(error.exception.code, 'immutable_cell')

    async def test_stale_context_cannot_override_new_generation(self):
        board = sized_board(9)
        await self.storage.save_board_state(self.lobby, self.name, board, None, 'lease')
        next_board = sized_board(16)
        next_board['public'].update(generationId='B', revision=2)
        self.assertEqual(await self.storage.save_board_state(self.lobby, self.name, next_board, ('A', 1), 'lease',
                                                           context={'allowedValues': allowed_values(16)}), 'saved')
        self.assertEqual(await self.storage.save_context_for_board(self.lobby, self.name, {'allowedValues': [1]}, ('A', 1), 'lease'), 'conflict')
        self.assertEqual((await self.storage.get_context(self.lobby, self.name))['allowedValues'], allowed_values(16))
        self.assertEqual(await self.storage.save_board_state(self.lobby, self.name, board, ('B', 2), 'lease',
                                                           context={}, expected_context=None), 'conflict')
        self.assertEqual((await self.storage.get_board_state(self.lobby, self.name))['public']['size'], 16)

    async def test_generation_and_context_are_atomic_9_16_9(self):
        service = SudokuV2Service(self.lobby, self.name, self.storage, 'lease')
        with patch.object(service, 'get_catalog', AsyncMock(return_value=CATALOG)):
            for size in (9, 16, 9):
                with patch.object(service, 'get_random_board', AsyncMock(return_value=sized_board(size))):
                    result = await service.generate_board({'size': size, 'difficulty': 'medium'})
                self.assertEqual(result['config']['allowedValues'], allowed_values(size))
                stored = await self.storage.get_board_state(self.lobby, self.name)
                self.assertEqual(stored['public']['size'], size)
                self.assertEqual((await self.storage.get_context(self.lobby, self.name))['allowedValues'], allowed_values(size))
                await service.set_context({'generationId': stored['public']['generationId'], 'preferences': {'size': 16}})
                if size == 9:
                    with self.assertRaises(SudokuV2Error) as error:
                        await service.set_value({'boardName': self.name, 'generationId': stored['public']['generationId'], 'cellIndex': 0, 'value': 10})
                    self.assertEqual(error.exception.code, 'invalid_value')
        old = sized_board(9)
        result = await self.storage.save_board_state(self.lobby, self.name, old, ('wrong', 0), 'lease', context={'allowedValues': [1]})
        self.assertEqual(result, 'conflict')
        self.assertEqual((await self.storage.get_context(self.lobby, self.name))['allowedValues'], allowed_values(9))

    async def test_delayed_context_from_previous_generation_is_rejected(self):
        service = SudokuV2Service(self.lobby, self.name, self.storage, 'lease')
        with patch.object(service, 'get_catalog', AsyncMock(return_value=CATALOG)):
            with patch.object(service, 'get_random_board', AsyncMock(return_value=sized_board(9))):
                first = await service.generate_board({'size': 9})
            delayed = {**first['config'], 'generationId': first['board']['generationId']}
            delayed['preferences']['showErrors'] = True
            with patch.object(service, 'get_random_board', AsyncMock(return_value=sized_board(16))):
                await service.generate_board({'size': 16})
            with self.assertRaises(SudokuV2Error) as error:
                await service.set_context(delayed)
            self.assertEqual(error.exception.code, 'stale_context')
            self.assertEqual((await self.storage.get_context(self.lobby, self.name))['allowedValues'], allowed_values(16))

    async def test_generation_config_is_private(self):
        await self.storage.release_presence(self.lobby, self.name, 'lease')
        with override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}), patch(
            'sudoku_v2.consumers.SudokuV2Storage', return_value=self.storage
        ), patch.object(SudokuV2Service, 'get_catalog', AsyncMock(return_value=CATALOG)), patch.object(
            SudokuV2Service, 'get_random_board', AsyncMock(return_value=sized_board(16))
        ):
            sockets = [WebsocketCommunicator(SudokuV2Consumer.as_asgi(), '/ws/sudoku-v2/') for _ in range(2)]
            for socket, name in zip(sockets, (self.name, 'Лена')):
                socket.scope['session'] = {'sudoku_v2_room': self.lobby, 'sudoku_v2_username': name}
                await socket.connect()
            await sockets[0].receive_json_from()
            try:
                await sockets[0].send_json_to({'kind': 'generate_board', 'data': {'size': 16}})
                own, other = await sockets[0].receive_json_from(), await sockets[1].receive_json_from()
                self.assertEqual(own['data']['config']['allowedValues'], allowed_values(16))
                self.assertNotIn('config', other['data'])
                self.assertNotIn('solution', str(other))
            finally:
                for socket in sockets:
                    await socket.disconnect()
