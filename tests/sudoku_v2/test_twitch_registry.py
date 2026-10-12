import asyncio
import os
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch
from django.test import override_settings
from . import test_bonuses, test_storage
from sudoku_v2.twitch.registry import TwitchRegistry, TwitchError
from sudoku_v2.twitch.service import TwitchService
from sudoku_v2.twitch.types import ExternalBonusCommand


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'),'Set an isolated test Redis URL')
class TwitchRegistryTests(IsolatedAsyncioTestCase):
    add_board=test_bonuses.BonusStorageTests.add_board

    async def asyncSetUp(self):
        await test_storage.StorageIntegrationTests.asyncSetUp(self)
        self.settings=override_settings(SUDOKU_V2_PREFIX='test-'+self.lobby)
        self.settings.enable()
        # The setup presence preceded the namespace override.
        await self.storage.acquire_presence(self.lobby,self.name,'lease')
        self.registry=TwitchRegistry(self.storage)
        self.publish=AsyncMock()
        self.service=TwitchService(self.registry,bot_id='bot',publish=self.publish)
        await self.add_board(self.name)
        await self.add_board('Лена')
        self.binding=await self.registry.register(self.lobby,self.name,'lease','Channel',0)

    async def asyncTearDown(self):
        keys=[key async for key in self.raw.scan_iter('test-'+self.lobby+'*')]
        if keys:await self.raw.delete(*keys)
        self.settings.disable()
        await test_storage.StorageIntegrationTests.asyncTearDown(self)

    def command(self,message_id='one',text='!blur',sent_at=None):
        return ExternalBonusCommand('twitch_chat',message_id,'channel','viewer',sent_at or self.binding['registeredAt'],text)

    async def test_register_updates_only_cooldown_and_preserves_last_applied(self):
        await self.service.handle(self.command())
        before=await self.registry.get('channel')
        updated=await self.registry.register(self.lobby,self.name,'lease','CHANNEL',25)
        self.assertEqual({k:v for k,v in updated.items() if k!='cooldownSeconds'},
                         {k:v for k,v in before.items() if k!='cooldownSeconds'})
        self.assertEqual(updated['cooldownSeconds'],25)
        self.assertIsNone(await self.service.handle(self.command('two')))
        self.assertEqual(await self.storage.get_active_usernames(self.lobby),{self.name,'Лена'})

    async def test_binding_cannot_be_stolen_and_only_owner_disconnects(self):
        with self.assertRaises(TwitchError):
            await self.registry.register(self.lobby,'Лена','Лена-lease','channel',0)
        with self.assertRaises(TwitchError):
            await self.registry.disconnect(self.lobby,'Лена','Лена-lease','channel')
        with self.assertRaises(TwitchError):
            await self.registry.register(self.lobby,self.name,'stale','channel',0)
        await self.registry.disconnect(self.lobby,self.name,'lease','channel')
        self.assertIsNone(await self.registry.get('channel'))

    async def test_concurrent_registration_other_rooms_has_one_owner(self):
        other=self.lobby+'-other'
        await self.storage.acquire_presence(other,'other','other-lease')
        await self.registry.disconnect(self.lobby,self.name,'lease','channel')
        results=await asyncio.gather(self.registry.register(self.lobby,self.name,'lease','channel',0),
            self.registry.register(other,'other','other-lease','channel',0),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(sum(isinstance(r,TwitchError) for r in results),1)

    async def test_zero_cooldown_distinct_and_duplicate_messages(self):
        # Separate adapters prove Redis deduplication, independently of the local channel lock.
        workers=[TwitchService(self.registry,bot_id='bot',publish=self.publish) for _ in range(4)]
        results=await asyncio.gather(*[worker.handle(self.command()) for worker in workers])
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertGreater(await self.raw.ttl(self.registry.dedup_key('bot','channel','one')),86390)
        results=await asyncio.gather(*[self.service.handle(self.command(str(i))) for i in range(20)])
        self.assertEqual(sum(r is not None for r in results),20)
        target=await self.storage.get_board_state(self.lobby,'Лена')
        self.assertEqual(len(target['public']['activeEffects']),21)
        self.assertEqual(self.publish.await_count,21)

    async def test_cooldown_change_during_apply_invalidates_old_candidate(self):
        await self.service.handle(self.command('first'))
        original=self.service.bonuses.apply_external
        async def update_then_apply(*args,**kwargs):
            await self.registry.register(self.lobby,self.name,'lease','channel',60)
            return await original(*args,**kwargs)
        with patch.object(self.service.bonuses,'apply_external',side_effect=update_then_apply):
            self.assertIsNone(await self.service.handle(self.command('second')))
        self.assertEqual(len((await self.storage.get_board_state(self.lobby,'Лена'))['public']['activeEffects']),1)
        self.assertIsNone(await self.raw.get(self.registry.dedup_key('bot','channel','second')))

    async def test_explicit_target_and_cooldown_validation(self):
        await self.add_board('Макс',16)
        event=await self.service.handle(self.command(text='!pulse Лена 1 999999'))
        self.assertEqual([b['name'] for b in event['targets']],['Лена'])
        effect=event['targets'][0]['activeEffects'][0]
        self.assertEqual(effect['expiresAt']-effect['startsAt'],30000)
        for value in [True,-1,86401,1.5,'5']:
            with self.subTest(value=value),self.assertRaises(TwitchError):
                await self.registry.register(self.lobby,self.name,'lease','channel',value)

    async def test_literal_name_punctuation_keeps_commands_targeted(self):
        for i,name in enumerate(["O'Brien",r'A\B']):
            await self.add_board(name)
            event=await self.service.handle(self.command(str(i),f'!blur {name} 3'))
            self.assertEqual([b['name'] for b in event['targets']],[name])
            self.assertEqual(event['params']['box'],2)
        self.assertEqual((await self.storage.get_board_state(self.lobby,'Лена'))['public']['activeEffects'],[])

    async def test_empty_invalid_missing_id_and_bot_message_do_not_consume(self):
        for command in [self.command('', '!blur'),self.command('unknown','!unknown'),
                        ExternalBonusCommand('twitch_chat','botmsg','channel','bot',self.binding['registeredAt'],'!blur')]:
            self.assertIsNone(await self.service.handle(command))
        await self.storage.release_presence(self.lobby,'Лена','Лена-lease')
        self.assertIsNone(await self.service.handle(self.command('empty')))
        self.assertEqual((await self.registry.get('channel'))['lastAppliedAt'],None)
        await self.add_board('Лена')
        self.assertIsNotNone(await self.service.handle(self.command('empty')))

    async def test_bad_name_and_args_default_once_for_mixed_targets(self):
        await self.add_board('Макс',16)
        event=await self.service.handle(self.command(text='!swap missing col 1 9'))
        self.assertEqual({b['name'] for b in event['targets']},{'Лена','Макс'})
        self.assertEqual(event['params']['axis'],'col')
        a,b=event['params']['first'],event['params']['second']
        self.assertEqual(a//3,b//3);self.assertEqual(a//4,b//4)
        self.assertEqual(event['source'],{'type':'twitch_chat','name':self.name})

    async def test_old_message_after_rebind_and_old_epoch_ignored(self):
        old=self.command('old',sent_at=self.binding['registeredAt']-1)
        await self.registry.disconnect(self.lobby,self.name,'lease','channel')
        await self.registry.register(self.lobby,self.name,'lease','channel',0)
        self.assertIsNone(await self.service.handle(old))
        await self.raw.set(self.storage._lobby_prefix(self.lobby)+':epoch','new-epoch')
        self.assertIsNone(await self.service.handle(self.command('stale')))
        self.assertEqual(await self.registry.list_active(),[])

    async def test_rebinding_during_apply_never_routes_old_message_to_new_binding(self):
        original=self.service.bonuses.apply_external
        first=True
        async def replace_then_apply(*args,**kwargs):
            nonlocal first
            if first:
                first=False
                await self.registry.disconnect(self.lobby,self.name,'lease','channel')
                # Disconnect and reconnect can share the millisecond timestamp.
                with patch('sudoku_v2.twitch.registry.time',return_value=self.binding['registeredAt']/1000):
                    await self.registry.register(self.lobby,self.name,'lease','channel',0)
            return await original(*args,**kwargs)
        with patch.object(self.service.bonuses,'apply_external',side_effect=replace_then_apply):
            self.assertIsNone(await self.service.handle(self.command()))
        self.assertEqual((await self.storage.get_board_state(self.lobby,'Лена'))['public']['activeEffects'],[])

    async def test_last_departure_removes_bindings_without_neighbor_collision(self):
        # A lobby called twitch must not share the global registry namespace.
        await self.storage.acquire_presence('twitch','neighbor','neighbor-lease')
        await self.registry.register('twitch','neighbor','neighbor-lease','neighbor',0)
        await self.storage.release_presence(self.lobby,'Лена','Лена-lease')
        await self.storage.release_presence(self.lobby,self.name,'lease')
        self.assertIsNone(await self.registry.get('channel'))
        self.assertIsNotNone(await self.registry.get('neighbor'))
