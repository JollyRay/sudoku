import os
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import patch
from channels.testing import WebsocketCommunicator

from .consumers import SudokuV2Consumer
from . import test_twitch_registry
from .user_context import normalize_context
from .test_gameplay import CATALOG


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'),'Set an isolated test Redis URL')
class TwitchAPITests(IsolatedAsyncioTestCase):
    add_board=test_twitch_registry.TwitchRegistryTests.add_board
    asyncSetUp=test_twitch_registry.TwitchRegistryTests.asyncSetUp
    asyncTearDown=test_twitch_registry.TwitchRegistryTests.asyncTearDown

    async def connect_player(self, name):
        token=await self.storage.get_presence_token(self.lobby,name)
        if token: await self.storage.release_presence(self.lobby,name,token)
        socket=WebsocketCommunicator(SudokuV2Consumer.as_asgi(),'/ws/sudoku-v2/')
        socket.scope['session']={'sudoku_v2_room':self.lobby,'sudoku_v2_username':name}
        self.assertTrue((await socket.connect())[0])
        return socket

    async def test_api_uses_session_owner_and_duplicate_only_updates_cooldown(self):
        with patch('sudoku_v2.consumers.SudokuV2Storage',return_value=self.storage):
            ws=await self.connect_player(self.name)
            try:
                for request,cd in [('one',15),('two',0)]:
                    await ws.send_json_to({'kind':'connect_twitch','data':{'requestId':request,'channel':'CHANNEL','cooldownSeconds':cd,'lobby':'forged','owner':'forged'}})
                    reply=await ws.receive_json_from()
                    self.assertEqual(reply['kind'],'twitch_status')
                    self.assertEqual(reply['data']['requestId'],request)
                    binding=(await self.registry.get('channel'))
                    self.assertEqual((binding['lobby'],binding['owner'],binding['bindingId'],binding['cooldownSeconds']),
                        (self.lobby,self.name,self.binding['bindingId'],cd))
                    self.assertEqual(reply['data']['bindings'][0]['owner'],self.name)
                    self.assertNotIn('solution',str(reply))
                for request in ['three','four']:
                    await ws.send_json_to({'kind':'disconnect_twitch','data':{'requestId':request,'channel':'channel'}})
                    self.assertEqual((await ws.receive_json_from())['data']['bindings'],[])
            finally: await ws.disconnect()

    async def test_other_owner_rejected_with_twitch_request_metadata(self):
        with patch('sudoku_v2.consumers.SudokuV2Storage',return_value=self.storage):
            ws=await self.connect_player('Лена')
            try:
                await ws.send_json_to({'kind':'disconnect_twitch','data':{'requestId':'bad','channel':'channel'}})
                error=(await ws.receive_json_from())['data']
                self.assertEqual((error['requestId'],error['requestKind'],error['code']),('bad','disconnect_twitch','binding_forbidden'))
                self.assertIsNotNone(await self.registry.get('channel'))
            finally: await ws.disconnect()

    async def test_invalid_cooldown_and_request_data_cannot_mutate_binding(self):
        with patch('sudoku_v2.consumers.SudokuV2Storage',return_value=self.storage):
            ws=await self.connect_player(self.name)
            try:
                for value in [True,-1,86401,'15',None]:
                    await ws.send_json_to({'kind':'connect_twitch','data':{'requestId':'bad','channel':'channel','cooldownSeconds':value}})
                    reply=await ws.receive_json_from()
                    self.assertEqual(reply['data']['code'],'invalid_cooldown')
                    self.assertEqual(reply['data']['requestKind'],'connect_twitch')
                self.assertEqual((await self.registry.get('channel'))['cooldownSeconds'],0)
            finally: await ws.disconnect()

    async def test_form_cooldown_is_only_a_preference(self):
        context=normalize_context({'preferences':{'twitchCooldown':15}},self.name,CATALOG)
        self.assertEqual(context['preferences']['twitchCooldown'],15)
        self.assertEqual((await self.registry.get('channel'))['cooldownSeconds'],0)

    async def test_active_worker_without_join_ack_is_connecting(self):
        from .service import SudokuV2Service
        await self.raw.set(self.registry.prefix+':active-worker','worker',ex=30)
        response=await SudokuV2Service(self.lobby,self.name,self.storage,'lease').get_twitch_status({})
        self.assertEqual(response['bindings'][0]['status'],'connecting')
        self.assertNotEqual(response['workerStatus'],'connected')
