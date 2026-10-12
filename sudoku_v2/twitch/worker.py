import asyncio
import json
import os
import re
from time import time
from uuid import uuid4

import requests
from channels.layers import get_channel_layer
from django.conf import settings

from common.redis import CommitGuard, ExpiringValue
from ..broadcast import room_group_name
from .irc import AuthError, TwitchIRCClient


async def validate_token(login, token):
    def request():
        try:
            response = requests.get('https://id.twitch.tv/oauth2/validate',
                headers={'Authorization': 'OAuth ' + token.removeprefix('oauth:')}, timeout=10)
            if response.status_code == 401:
                raise AuthError()
            if response.status_code != 200:
                raise ConnectionError('Token validation unavailable')
            data = response.json()
            if (data.get('login') != login or not data.get('user_id') or
                    'chat:read' not in data.get('scopes', []) or data.get('expires_in', 0) <= 0):
                raise AuthError()
            return str(data['user_id'])
        except (requests.RequestException, ValueError):
            raise ConnectionError('Token validation unavailable') from None
    return await asyncio.to_thread(request)


class TwitchWorker:
    def __init__(self, registry, service, *, login, token, client=None, validate=validate_token,
                 renew_seconds=10, validate_seconds=3600):
        self.registry, self.service = registry, service
        self.login, self.token = login, token
        self.client, self.validate = client, validate
        self.renew_seconds, self.validate_seconds = renew_seconds, validate_seconds
        self.lease_token = uuid4().hex
        self.status_cache = {}

    @property
    def lease_key(self):
        return self.registry.prefix + ':lease:' + self.service.bot_id

    @property
    def guard(self):
        return CommitGuard(self.lease_key, 'string', self.lease_token)

    @property
    def active_key(self):
        return self.registry.prefix + ':active-worker'

    @property
    def guards(self):
        return [self.guard, CommitGuard(self.active_key, 'string', self.lease_token)]

    def lease_values(self):
        return {key: ExpiringValue(self.lease_token, 30) for key in (self.lease_key, self.active_key)}

    async def acquire(self):
        return await self.registry.redis.compare_and_write_batch(
            [CommitGuard(key, 'string', None) for key in (self.lease_key, self.active_key)], {},
            self.lease_values()) == 'saved'

    async def release(self):
        await self.registry.redis.compare_and_write_batch(self.guards, {self.lease_key: {}, self.active_key: {}}, {})

    async def on_status(self, binding, status, reason, *, guards=None):
        value = {'bindingId': binding['bindingId'], 'channel': binding['channel'], 'status': status,
               'reason': reason, 'updatedAt': int(time() * 1000)}
        checks = self.guards if guards is None else list(guards)
        checks.append(CommitGuard(self.registry.binding_key(binding['channel']), 'hash',
                                  {'bindingId': json.dumps(binding['bindingId'])}))
        result = await self.registry.redis.compare_and_write_batch(checks, {},
            {self.registry.status_key(binding): ExpiringValue(json.dumps(value), 86400 if status in ('auth_error', 'disabled') else 45)})
        cached = (binding['bindingId'], status, reason)
        if result == 'saved' and self.status_cache.get(binding['channel']) != cached:
            self.status_cache[binding['channel']] = cached
            await get_channel_layer().group_send(room_group_name(binding['lobby']), {
                'type': 'forward_message', 'message': {'kind': 'twitch_status', 'data': value}})

    async def on_message(self, command, binding):
        # Fence both the transport's binding snapshot and the worker, inside effect EXEC.
        await self.service.handle(command, guards=[*self.guards, CommitGuard(
            self.registry.binding_key(binding['channel']), 'hash', {'bindingId': json.dumps(binding['bindingId'])})])

    async def run(self, stop_event):
        delay = 1
        while not stop_event.is_set():
            try:
                self.service.bot_id = await self.validate(self.login, self.token)
                break
            except AuthError:
                # Startup has no lease yet. Do not overwrite a running worker's status.
                for binding in await self.registry.list_active():
                    await self.on_status(binding, 'auth_error', 'authentication', guards=[
                        CommitGuard(self.active_key, 'string', None)])
                return
            except ConnectionError:
                for binding in await self.registry.list_active():
                    await self.on_status(binding, 'error', 'validation_unavailable', guards=[
                        CommitGuard(self.active_key, 'string', None)])
                try:
                    await asyncio.wait_for(stop_event.wait(), delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(30, delay * 2)
        while not stop_event.is_set():
            if await self.acquire():
                break
            # A crashed process leaves a lease for up to 30s. Stay available for takeover.
            try:
                await asyncio.wait_for(stop_event.wait(), min(2, self.renew_seconds))
            except asyncio.TimeoutError:
                pass
        else:
            return
        client = self.client or TwitchIRCClient(self.login, self.token, self.service.bot_id,
            max_channels=getattr(settings, 'TWITCH_MAX_CHANNELS', 100),
            join_limit=getattr(settings, 'TWITCH_JOIN_LIMIT', 20), auth_limit=getattr(settings, 'TWITCH_AUTH_LIMIT', 20))

        async def renew():
            while True:
                await asyncio.sleep(self.renew_seconds)
                if await self.registry.redis.compare_and_write_batch(self.guards, {}, self.lease_values()) != 'saved':
                    return

        async def validate_hourly():
            while True:
                await asyncio.sleep(self.validate_seconds)
                # A validation outage stops this transport; a supervisor may retry safely.
                if await self.validate(self.login, self.token) != self.service.bot_id:
                    raise AuthError()

        tasks = []
        final_status = ('disabled', 'stopped')
        try:
            tasks = [
                asyncio.create_task(client.run(self.registry.list_active, self.on_message, self.on_status)),
                asyncio.create_task(renew()),
                asyncio.create_task(validate_hourly()),
                asyncio.create_task(stop_event.wait()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except AuthError:
            final_status = ('auth_error', 'authentication')
        except Exception:
            final_status = ('error', 'worker_unavailable')
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                for binding in await self.registry.list_active():
                    await self.on_status(binding, *final_status)
            finally:
                await self.release()
        return final_status[0]


async def run_twitch_worker(registry, service, *, stop_event):
    if not getattr(settings, 'TWITCH_BOT_ENABLED', True):
        raise ValueError('Twitch worker disabled')
    login = os.environ.get('SUDOKU_V2_TWITCH_LOGIN', '').strip().lower()
    token = os.environ.get('SUDOKU_V2_TWITCH_TOKEN', '').strip()
    if not re.fullmatch(r'[a-z0-9_]{1,25}', login) or not re.fullmatch(r'(?:oauth:)?[a-zA-Z0-9]+', token):
        raise ValueError('Set SUDOKU_V2_TWITCH_LOGIN and SUDOKU_V2_TWITCH_TOKEN in the environment')
    return await TwitchWorker(registry, service, login=login, token=token).run(stop_event)
