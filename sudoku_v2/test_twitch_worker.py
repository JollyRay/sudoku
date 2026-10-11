import asyncio
import importlib
import os
from unittest import IsolatedAsyncioTestCase, TestCase, skipUnless
from unittest.mock import AsyncMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from .twitch.irc import AuthError, RateWindow, TwitchIRCClient, parse_irc_line
from .twitch.worker import TwitchWorker, validate_token
from . import test_twitch_registry


class IRCParsingTests(TestCase):
    def test_tags_unicode_and_ping(self):
        message = parse_irc_line(r'@id=m1;display-name=A\sB\:C\\D;empty :viewer!v@h PRIVMSG #channel :!blur "Игрок 2" 3')
        self.assertEqual(message.tags, {'id':'m1', 'display-name':'A B;C\\D', 'empty':''})
        self.assertEqual(message.params, ['#channel', '!blur "Игрок 2" 3'])
        self.assertEqual(parse_irc_line('PING :tmi.twitch.tv').params, ['tmi.twitch.tv'])
        self.assertIsNone(parse_irc_line('@tags-only'))

    def test_limits_with_fake_clock(self):
        now = [0]
        limit = RateWindow(20, 10, clock=lambda:now[0])
        self.assertTrue(all(limit.take() for _ in range(20)))
        self.assertFalse(limit.take())
        now[0] = 9.99
        self.assertFalse(limit.take())
        now[0] = 10
        self.assertTrue(limit.take())

    def test_worker_settings_do_not_load_destructive_ready_hooks(self):
        module = importlib.import_module('sudoku_v2.worker_settings')
        self.assertNotIn('game.apps.GameConfig', module.INSTALLED_APPS)
        self.assertNotIn('voice.apps.VoiceConfig', module.INSTALLED_APPS)

    @override_settings(TWITCH_BOT_ENABLED=False)
    def test_disabled_command_refuses_before_token_or_transport(self):
        with patch('sudoku_v2.management.commands.run_twitch_bot.run_twitch_worker', new_callable=AsyncMock) as run:
            with self.assertRaisesRegex(CommandError, 'disabled'):
                call_command('run_twitch_bot')
            run.assert_not_called()


class FakeWriter:
    def __init__(self): self.lines=[]; self.closed=False
    def write(self, data): self.lines.append(data.decode())
    async def drain(self): pass
    def close(self): self.closed=True
    async def wait_closed(self): pass


async def eventually(predicate):
    for _ in range(200):
        if predicate(): return
        await asyncio.sleep(.005)
    raise AssertionError('Condition not reached')


class IRCTransportTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.streams=[]; self.writers=[]
        async def connect(*args, **kwargs):
            stream=asyncio.StreamReader(); writer=FakeWriter()
            self.streams.append(stream); self.writers.append(writer)
            return stream,writer
        self.desired={'channel': {'channel':'channel','bindingId':'b1'}}
        self.provider=AsyncMock(side_effect=lambda:list(self.desired.values()))
        self.status=AsyncMock(); self.message=AsyncMock()
        self.client=TwitchIRCClient('botlogin','dummy','bot',connect=connect,reconcile_seconds=.01,join_timeout=.08,retry_seconds=.01)
        self.task=asyncio.create_task(self.client.run(self.provider,self.message,self.status))
        await eventually(lambda: bool(self.writers))

    async def asyncTearDown(self):
        self.task.cancel()
        await asyncio.gather(self.task,return_exceptions=True)

    async def welcome(self):
        self.streams[-1].feed_data(b':tmi 001 botlogin :Welcome\r\n')
        await eventually(lambda: 'JOIN #channel\r\n' in self.writers[-1].lines)

    async def test_fragmented_stream_ping_echo_and_privmsg(self):
        await self.welcome()
        self.assertFalse(any(c.args[1]=='connected' for c in self.status.call_args_list))
        self.streams[0].feed_data(b'PING :tmi.twi')
        self.streams[0].feed_data(b'tch.tv\r\n:botlogin!b@h JOIN #channel\r\n')
        self.streams[0].feed_data('@id=m1;user-id=viewer;tmi-sent-ts=123 :v!v@h PRIVMSG #channel :!blur "Игрок 2" 3\r\n@id=m2;user-id=bot;tmi-sent-ts=124 :botlogin!b@h PRIVMSG #channel :!rotate\r\n'.encode())
        await eventually(lambda:self.message.call_count==1)
        self.assertIn('PONG :tmi.twitch.tv\r\n',self.writers[0].lines)
        command,binding=self.message.call_args.args
        self.assertEqual((command.message_id,command.sent_at_ms,command.text,binding['bindingId']),('m1',123,'!blur "Игрок 2" 3','b1'))

    async def test_registry_update_no_rejoin_disconnect_parts_one(self):
        await self.welcome()
        self.streams[0].feed_data(b':botlogin!b@h JOIN #channel\r\n')
        self.desired['second']={'channel':'second','bindingId':'b2'}
        await eventually(lambda:'JOIN #second\r\n' in self.writers[0].lines)
        self.desired['channel']['cooldownSeconds']=25
        await asyncio.sleep(.04)
        self.assertEqual(self.writers[0].lines.count('JOIN #channel\r\n'),1)
        del self.desired['channel']
        await eventually(lambda:'PART #channel\r\n' in self.writers[0].lines)
        self.assertNotIn('PART #second\r\n',self.writers[0].lines)

    async def test_reconnect_resubscribes_and_join_timeout_no_spam(self):
        await self.welcome()
        await eventually(lambda:any(c.args[1:]==('error','join_timeout') for c in self.status.call_args_list))
        self.assertEqual(self.writers[0].lines.count('JOIN #channel\r\n'),1)
        self.streams[0].feed_data(b':tmi RECONNECT\r\n')
        await eventually(lambda:len(self.writers)==2)
        await self.welcome()
        self.assertTrue(self.writers[0].closed)

    async def test_auth_failure_stops_without_echoing_server_text(self):
        self.streams[0].feed_data(b':tmi NOTICE * :Login authentication failed\r\n')
        with self.assertRaises(AuthError): await self.task
        self.assertTrue(self.writers[0].closed)
        self.assertEqual(len(self.writers),1)

    async def test_channel_cap_and_join_rate_queue(self):
        self.client.max_channels=1
        self.desired['second']={'channel':'second','bindingId':'b2'}
        await self.welcome()
        await eventually(lambda:any(c.args[1:]==('error','channel_limit') for c in self.status.call_args_list))
        self.assertNotIn('JOIN #second\r\n',self.writers[0].lines)
        del self.desired['channel']
        await eventually(lambda:'JOIN #second\r\n' in self.writers[0].lines)

    async def test_binding_replacement_fences_old_ack_with_new_stream(self):
        await self.welcome()
        self.desired['channel']={'channel':'channel','bindingId':'new'}
        await eventually(lambda:len(self.writers)==2)
        self.streams[0].feed_data(b':botlogin!b@h JOIN #channel\r\n')
        await self.welcome()
        self.assertFalse(any(c.args[0]['bindingId']=='new' and c.args[1]=='connected' for c in self.status.call_args_list))

    async def test_part_then_rebind_fences_old_join_ack(self):
        await self.welcome()
        del self.desired['channel']
        await eventually(lambda:'PART #channel\r\n' in self.writers[0].lines)
        self.desired['channel']={'channel':'channel','bindingId':'new'}
        await eventually(lambda:len(self.writers)==2)
        self.streams[0].feed_data(b':botlogin!b@h JOIN #channel\r\n')
        await self.welcome()
        self.assertFalse(any(c.args[0]['bindingId']=='new' and c.args[1]=='connected' for c in self.status.call_args_list))


class IRCBackoffTests(IsolatedAsyncioTestCase):
    async def test_network_retry_backoff_is_bounded(self):
        delays=[]
        async def sleep(seconds):
            delays.append(seconds)
            if len(delays)==7: raise asyncio.CancelledError()
        client=TwitchIRCClient('botlogin','dummy','bot',connect=AsyncMock(side_effect=OSError()))
        with patch('sudoku_v2.twitch.irc.asyncio.sleep',side_effect=sleep):
            with self.assertRaises(asyncio.CancelledError):
                await client.run(AsyncMock(return_value=[]),AsyncMock(),AsyncMock())
        self.assertEqual(delays,[1,2,4,8,16,30,30])


@skipUnless(os.environ.get('SUDOKU_V2_TEST_REDIS_URL'),'Set an isolated test Redis URL')
class TwitchWorkerTests(IsolatedAsyncioTestCase):
    add_board=test_twitch_registry.TwitchRegistryTests.add_board
    asyncSetUp=test_twitch_registry.TwitchRegistryTests.asyncSetUp
    asyncTearDown=test_twitch_registry.TwitchRegistryTests.asyncTearDown
    command=test_twitch_registry.TwitchRegistryTests.command

    def worker(self, **kwargs):
        return TwitchWorker(self.registry,self.service,login='botlogin',token='dummy',
            validate=AsyncMock(return_value='bot'),renew_seconds=.01,**kwargs)

    async def test_lease_loss_fences_commands_and_cancels_transport(self):
        client=AsyncMock(); started=asyncio.Event()
        async def run(provider,on_message,on_status):
            started.set()
            await asyncio.Future()
        client.run.side_effect=run
        worker=self.worker(client=client)
        task=asyncio.create_task(worker.run(asyncio.Event()))
        await started.wait()
        await self.raw.set(worker.lease_key,'replacement',ex=30)
        await worker.on_message(self.command(),self.binding)
        self.assertEqual(self.publish.call_count,0)
        await asyncio.wait_for(task,1)
        self.assertEqual(await self.raw.get(worker.lease_key),'replacement')

    async def test_restart_waits_for_crashed_workers_lease(self):
        previous=self.worker()
        await previous.acquire()
        await self.raw.expire(previous.lease_key,1)
        await self.raw.expire(previous.active_key,1)
        client=AsyncMock(); stop=asyncio.Event()
        async def run(*args): stop.set()
        client.run.side_effect=run
        worker=self.worker(client=client)
        await asyncio.wait_for(worker.run(stop),2)
        self.assertEqual(client.run.await_count,1)

    async def test_two_lobbies_and_stale_status_binding_guard(self):
        worker=self.worker()
        self.assertTrue(await worker.acquire())
        other=self.lobby+'-second'
        await self.storage.acquire_presence(other,'host','host-lease')
        original=self.lobby
        self.lobby=other
        await self.add_board('host'); await self.add_board('opponent')
        second=await self.registry.register(other,'host','host-lease','second',0)
        self.lobby=original
        from .twitch.types import ExternalBonusCommand
        await worker.on_message(self.command(),self.binding)
        await worker.on_message(ExternalBonusCommand('twitch_chat','two','second','viewer',second['registeredAt'],'!rotate'),second)
        self.assertEqual([c.args[0] for c in self.publish.call_args_list],[original,other])
        await self.registry.disconnect(original,self.name,'lease','channel')
        new=await self.registry.register(original,self.name,'lease','channel',0)
        await worker.on_status(self.binding,'connected','')
        self.assertIsNone(await self.registry.get_status(new))
        await worker.release()

    async def test_validation_hourly_and_invalid_stops(self):
        client=AsyncMock()
        async def run(*args): await asyncio.Future()
        client.run.side_effect=run
        worker=self.worker(client=client,validate_seconds=.02)
        worker.validate=AsyncMock(side_effect=['bot',AuthError()])
        await asyncio.wait_for(worker.run(asyncio.Event()),1)
        self.assertEqual(worker.validate.await_count,2)
        self.assertEqual((await self.registry.get_status(self.binding))['status'],'auth_error')
        self.assertIsNone(await self.raw.get(worker.lease_key))

    async def test_validate_401_and_network_errors_do_not_expose_credentials(self):
        response=type('Response',(),{'status_code':401})()
        with patch('sudoku_v2.twitch.worker.requests.get',return_value=response) as get:
            with self.assertRaises(AuthError): await validate_token('botlogin','sensitive')
            self.assertEqual(get.call_args.kwargs['timeout'],10)
        import requests
        with patch('sudoku_v2.twitch.worker.requests.get',side_effect=requests.Timeout('sensitive')):
            with self.assertRaisesRegex(ConnectionError,'^Token validation unavailable$'):
                await validate_token('botlogin','sensitive')

    async def test_invalid_startup_token_never_starts_transport(self):
        client=AsyncMock(); worker=self.worker(client=client)
        worker.validate=AsyncMock(side_effect=AuthError())
        await worker.run(asyncio.Event())
        client.run.assert_not_called()
        self.assertEqual((await self.registry.get_status(self.binding))['status'],'auth_error')

    async def test_invalid_restart_overwrites_disabled_but_not_live_worker(self):
        previous=self.worker()
        await previous.acquire()
        await previous.on_status(self.binding,'disabled','stopped')
        await previous.release()
        failed=self.worker(client=AsyncMock())
        failed.validate=AsyncMock(side_effect=AuthError())
        await failed.run(asyncio.Event())
        self.assertEqual((await self.registry.get_status(self.binding))['status'],'auth_error')
        await previous.acquire()
        await previous.on_status(self.binding,'connected','')
        await failed.run(asyncio.Event())
        self.assertEqual((await self.registry.get_status(self.binding))['status'],'connected')
        await previous.release()

    async def test_network_validation_retries_and_stop_interrupts_backoff(self):
        stop=asyncio.Event(); client=AsyncMock(); worker=self.worker(client=client)
        async def validate(*args): stop.set(); raise ConnectionError('unavailable')
        worker.validate=validate
        await asyncio.wait_for(worker.run(stop),1)
        client.run.assert_not_called()
        self.assertEqual((await self.registry.get_status(self.binding))['reason'],'validation_unavailable')
