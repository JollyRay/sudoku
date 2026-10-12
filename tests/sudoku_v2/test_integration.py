"""Real Redis + Channels + fake IRC. Never contacts Twitch or the production DB."""
import asyncio
import os
from time import time
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch

from channels.testing import WebsocketCommunicator
from sudoku_v2.broadcast import publish_bonus
from sudoku_v2.consumers import SudokuV2Consumer
from sudoku_v2.service import SudokuV2Service
from .support import CATALOG, FakeWriter, TwitchFixture, eventually
from sudoku_v2.twitch.irc import TwitchIRCClient
from sudoku_v2.twitch.worker import TwitchWorker


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'),'Set an isolated test Redis URL')
class EndToEndTests(TwitchFixture, IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.sockets=[]
        self.storage_patch=patch('sudoku_v2.consumers.SudokuV2Storage',return_value=self.storage)
        self.catalog_patch=patch.object(SudokuV2Service,'get_catalog',AsyncMock(return_value={**CATALOG,'sizes':[9,16]}))
        self.storage_patch.start();self.catalog_patch.start()

    async def asyncTearDown(self):
        try:
            for socket in self.sockets: await socket.disconnect()
        finally:
            self.catalog_patch.stop();self.storage_patch.stop()
            await super().asyncTearDown()

    async def player(self, name, lobby=None):
        lobby=lobby or self.lobby
        token=await self.storage.get_presence_token(lobby,name)
        if token: await self.storage.release_presence(lobby,name,token)
        socket=WebsocketCommunicator(SudokuV2Consumer.as_asgi(),'/ws/sudoku-v2/')
        socket.scope['session']={'sudoku_v2_room':lobby,'sudoku_v2_username':name}
        self.assertTrue((await socket.connect())[0]);self.sockets.append(socket)
        return socket

    async def drain(self, *sockets):
        for socket in sockets:
            while not await socket.receive_nothing(timeout=.02): await socket.receive_json_from()

    async def receive(self, socket, kind, request_id=None):
        for _ in range(30):
            message=await socket.receive_json_from(timeout=2)
            if message['kind']==kind and (request_id is None or message['data'].get('requestId')==request_id): return message['data']
        self.fail('Expected message not received: '+kind)

    async def no_bonus(self, socket):
        # Health/status notifications can still be in flight between async consumers.
        # They must never conceal a wrongly routed or duplicated game event.
        for _ in range(30):
            if await socket.receive_nothing(timeout=.1): return
            self.assertNotEqual((await socket.receive_json_from())['kind'],'bonus_applied')
        self.fail('Status notifications did not settle')

    async def test_cell_bonus_reconnect_mixed_sizes(self):
        await self.add_board('Макс',16)
        source=await self.player(self.name);nine=await self.player('Лена');sixteen=await self.player('Макс')
        await self.drain(*self.sockets)
        answer=(await self.storage.get_board_state(self.lobby,self.name))['solution']['0']
        move={'boardName':self.name,'generationId':'A','cellIndex':0,'value':answer}
        await source.send_json_to({'kind':'set_value','data':move})
        ack=await self.receive(source,'set_value')
        self.assertEqual(ack['board']['consumedBonusCells'],[0])
        event9=await self.receive(nine,'bonus_applied');event16=await self.receive(sixteen,'bonus_applied')
        self.assertEqual(event9['params'],event16['params'])
        self.assertEqual(event9['eventId'],event16['eventId'])
        targets={b['name']:b for b in event9['targets']}
        self.assertEqual((targets['Лена']['size'],targets['Макс']['size']),(9,16))
        original=targets['Макс']['activeEffects'][0]
        await sixteen.disconnect();self.sockets.remove(sixteen)
        sixteen=await self.player('Макс')
        await sixteen.send_json_to({'kind':'get_board_data','data':{}})
        snapshot=await self.receive(sixteen,'board_data')
        self.assertEqual(snapshot['board']['activeEffects'][0],original)
        self.assertLess(original['expiresAt']-snapshot['serverNow'],30000)
        await self.drain(*self.sockets)
        for value in ['',answer]:
            await source.send_json_to({'kind':'set_value','data':{**move,'value':value}})
            await self.receive(source,'set_value');await self.receive(nine,'set_value');await self.receive(sixteen,'set_value')
        self.assertTrue(await nine.receive_nothing(timeout=.05))
        self.assertEqual(len((await self.storage.get_board_state(self.lobby,'Макс'))['public']['activeEffects']),1)
        before=await self.storage.get_board_state(self.lobby,self.name)
        await source.send_json_to({'kind':'set_value','data':{**move,'generationId':'old','value':''}})
        rejection=await source.receive_json_from()
        self.assertEqual(rejection['kind'],'error')
        self.assertEqual(rejection['data']['code'],'stale_generation')
        self.assertEqual(await self.storage.get_board_state(self.lobby,self.name),before)

    async def test_twitch_two_rooms_lifecycle(self):
        owner=await self.player(self.name);target=await self.player('Лена')
        first_lobby=self.lobby;other_lobby=self.lobby+'-other'
        self.lobby=other_lobby
        await self.storage.acquire_presence(other_lobby,'Другой','Другой-lease')
        await self.add_board('Другой');await self.add_board('Другой соперник',16)
        self.lobby=first_lobby
        other=await self.player('Другой соперник',other_lobby)
        await self.registry.register(other_lobby,'Другой','Другой-lease','second',0)
        self.service.publish=publish_bonus
        worker=TwitchWorker(self.registry,self.service,login='botlogin',token='fake')
        self.assertTrue(await worker.acquire())
        reader=asyncio.StreamReader();writer=FakeWriter()
        original_write=writer.write
        def write(data):
            original_write(data)
            if data.startswith(b'JOIN '): reader.feed_data(b':botlogin!b@h '+data)
        writer.write=write
        async def connect(*args,**kwargs):
            reader.feed_data(b':tmi 001 botlogin :Welcome\r\n');return reader,writer
        joined=set()
        processed=[]
        async def status(binding,state,reason):
            await worker.on_status(binding,state,reason)
            if state=='connected': joined.add(binding['channel'])
        client=TwitchIRCClient('botlogin','fake','bot',connect=connect,reconcile_seconds=.01)
        async def on_message(command,binding):
            await worker.on_message(command,binding)
            processed.append(command.message_id)
        transport=asyncio.create_task(client.run(self.registry.list_active,on_message,status))
        def chat(message_id,channel='channel',timestamp=None):
            timestamp=timestamp or int(time()*1000)
            reader.feed_data(f'@id={message_id};user-id=viewer;tmi-sent-ts={timestamp} :viewer!v@h PRIVMSG #{channel} :!blur * 3\r\n'.encode())
        try:
            await eventually(lambda:len(joined)==2)
            await self.drain(*self.sockets)
            chat('first');event=await self.receive(target,'bonus_applied');await self.receive(owner,'bonus_applied')
            self.assertEqual(event['params']['box'],2)
            await self.no_bonus(other)
            chat('first')
            await eventually(lambda:processed.count('first')==2)
            await self.no_bonus(target)
            await owner.send_json_to({'kind':'connect_twitch','data':{'requestId':'cd','channel':'channel','cooldownSeconds':15}})
            await self.receive(owner,'twitch_status','cd');await self.drain(target)
            self.assertEqual((await self.registry.get('channel'))['bindingId'],self.binding['bindingId'])
            chat('cooldown')
            await eventually(lambda:'cooldown' in processed)
            await self.no_bonus(target)
            chat('second-room','second');await self.receive(other,'bonus_applied')
            await self.no_bonus(target)
            await owner.send_json_to({'kind':'disconnect_twitch','data':{'requestId':'bye','channel':'channel'}})
            await self.receive(owner,'twitch_status','bye');await self.drain(target)
            await eventually(lambda:'PART #channel\r\n' in writer.lines)
            chat('after-part')
            await self.no_bonus(target)
        finally:
            transport.cancel();await asyncio.gather(transport,return_exceptions=True);await worker.release()
        # Re-create the same room code: neither an old binding nor an old packet moves with it.
        old_epoch=await self.storage.get_room_epoch(first_lobby)
        await owner.disconnect();self.sockets.remove(owner)
        await target.disconnect();self.sockets.remove(target)
        self.assertIsNone(await self.registry.get('channel'))
        await self.storage.acquire_presence(first_lobby,self.name,'lease')
        await self.add_board(self.name);await self.add_board('Лена')
        new_binding=await self.registry.register(first_lobby,self.name,'lease','channel',0)
        self.assertNotEqual(new_binding['roomEpoch'],old_epoch)
        from sudoku_v2.twitch.types import ExternalBonusCommand
        result=await self.service.handle(ExternalBonusCommand('twitch_chat','never-applied','channel','viewer',self.binding['registeredAt']-1,'!blur'))
        self.assertIsNone(result)
        self.assertEqual((await self.storage.get_board_state(first_lobby,'Лена'))['public']['activeEffects'],[])
