import asyncio
import json
import secrets
from contextlib import suppress
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from .service import SudokuV2Error, SudokuV2Service
from .storage import SudokuV2Storage
from .broadcast import room_group_name, publish_bonus
from .twitch.registry import TwitchError


class SudokuV2Consumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    request_routes = {
        "get_board_data": ("board_data", False),
        "set_value": ("set_value", True),
        "set_context": ("context_data", False),
        "generate_board": ("board_data", True),
        "connect_twitch": ("twitch_status", False),
        "disconnect_twitch": ("twitch_status", False),
        "get_twitch_status": ("twitch_status", False),
    }

    async def connect(self) -> None:
        self.group_joined = False
        self.presence_acquired = False
        self.presence_task = None
        session = self.scope.get("session", {})
        lobby = session.get("sudoku_v2_room")
        username = session.get("sudoku_v2_username")
        if not isinstance(lobby, str) or not lobby or not isinstance(username, str) or not username:
            # Complete the handshake so browsers receive the application close
            # code instead of an HTTP 403 reported as an opaque 1006 error.
            await self.accept()
            await self.close(code=4401)
            return

        self.lobby = lobby
        self.username = username
        self.group_name = room_group_name(lobby)
        self.connection_id = secrets.token_urlsafe(32)
        self.storage = SudokuV2Storage()
        self.presence_acquired = await self.storage.acquire_presence(
            lobby,
            username,
            self.connection_id,
        )
        if not self.presence_acquired:
            await self.accept()
            await self.close(code=4409)
            return

        self.service = SudokuV2Service(
            lobby,
            username,
            self.storage,
            self.connection_id,
        )
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.group_joined = True
            await self.accept()
            await self.broadcast_participants_changed()
        except BaseException:
            if self.group_joined:
                with suppress(Exception):
                    await self.channel_layer.group_discard(
                        self.group_name,
                        self.channel_name,
                    )
            await self.release_presence()
            raise

        self.presence_task = asyncio.create_task(self.keep_presence_alive())

    async def broadcast_participants_changed(self) -> None:
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "participants_changed", "sender": self.channel_name},
        )

    async def participants_changed(self, event: dict[str, Any]) -> None:
        if event.get("sender") == self.channel_name:
            return
        # Read current membership instead of replaying an old join/leave delta.
        # A delayed departure event cannot hide a player who has since rejoined.
        boards = await self.service.get_participant_boards()
        await self.send(text_data=json.dumps({"kind": "participants_data", "data": {
            "boards": boards, "serverNow": self.service.now_ms(),
        }}))

    async def disconnect(self, close_code: int) -> None:
        if self.presence_task is not None:
            self.presence_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.presence_task

        try:
            if self.group_joined:
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name,
                )
        finally:
            await self.release_presence()

    async def keep_presence_alive(self) -> None:
        renewal_interval = self.storage.PRESENCE_EXPIRY_SECONDS / 3
        while True:
            await asyncio.sleep(renewal_interval)
            try:
                renewed = await self.storage.renew_presence(
                    self.lobby,
                    self.username,
                    self.connection_id,
                )
            except Exception:
                await self.close(code=1011)
                return

            if not renewed:
                await self.close(code=4409)
                return

    async def release_presence(self) -> None:
        if not self.presence_acquired:
            return

        try:
            await self.storage.release_presence(
                self.lobby,
                self.username,
                self.connection_id,
            )
            # Refresh membership even if this lease already expired. Recipients
            # fetch current presence, so a replacement connection stays visible.
            await self.broadcast_participants_changed()
        finally:
            self.presence_acquired = False

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        if text_data is None:
            await self.send_error("invalid_message", "Сообщение должно содержать текст JSON.")
            return

        try:
            envelope = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("invalid_json", "Не удалось прочитать JSON сообщения.")
            return

        if not isinstance(envelope, dict):
            await self.send_error("invalid_message", "Сообщение должно быть объектом.")
            return

        kind = envelope.get("kind")
        data = envelope.get("data", {})
        if kind in ('connect_twitch','disconnect_twitch','get_twitch_status') and not isinstance(data,dict):
            await self.send_error('invalid_message','Неверные данные Twitch.',requestKind=kind,requestId=None)
            return
        if not isinstance(kind, str) or not isinstance(data, dict):
            await self.send_error("invalid_message", "Неверный тип сообщения или данных.")
            return

        if kind not in self.request_routes:
            await self.send_error("invalid_message", "Неизвестный тип сообщения.")
            return

        await self.dispatch_request(kind, data)

    async def dispatch_request(
        self,
        kind: str,
        data: dict[str, Any],
    ) -> None:
        if not await self.ensure_current_presence():
            return

        response_kind, broadcast = self.request_routes[kind]
        handler = getattr(self.service, kind)
        twitch_request=response_kind=='twitch_status'

        try:
            if twitch_request and (not isinstance(data.get('requestId'),str) or not 1<=len(data['requestId'])<=128):
                raise TwitchError('invalid_request','Неверный идентификатор запроса Twitch.')
            response_data = await handler(data)
        except (SudokuV2Error,TwitchError) as error:
            if error.code == "connection_replaced":
                await self.close(code=4409)
            else:
                await self.send_error(error.code, error.message,**({'requestId':data.get('requestId'),'requestKind':kind} if twitch_request else {}))
            return

        bonus_event = response_data.pop('_bonus_event', None)
        message = {"kind": response_kind, "data": response_data}
        await self.send(text_data=json.dumps(message))
        if twitch_request and kind!='get_twitch_status':
            await self.channel_layer.group_send(self.group_name,{'type':'twitch_changed','sender':self.channel_name})
        if bonus_event:
            await publish_bonus(self.lobby, bonus_event, channel_layer=self.channel_layer)
        elif broadcast:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "forward_message",
                    "sender": self.channel_name,
                    "message": {"kind": response_kind, "data": {key: value for key, value in response_data.items() if key != 'config'}},
                },
            )

    async def ensure_current_presence(self) -> bool:
        try:
            renewed = await self.storage.renew_presence(
                self.lobby,
                self.username,
                self.connection_id,
            )
        except Exception:
            await self.send_error(
                "presence_unavailable",
                "Не удалось проверить подключение. Подключитесь повторно.",
            )
            await self.close(code=1011)
            return False

        if renewed:
            return True

        await self.close(code=4409)
        return False

    async def forward_message(self, event: dict[str, Any]) -> None:
        if event.get("sender") == self.channel_name:
            return
        if event['message'].get('kind')=='twitch_status':
            await self.twitch_changed(event)
            return
        await self.send(text_data=json.dumps(event["message"]))

    async def twitch_changed(self, event):
        if event.get('sender')==self.channel_name: return
        data=await self.service.get_twitch_status({})
        await self.send(text_data=json.dumps({'kind':'twitch_status','data':data}))

    async def send_error(self, code: str, message: str, **metadata) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "kind": "error",
                    "data": {"code": code, "message": message, **metadata},
                }
            )
        )
