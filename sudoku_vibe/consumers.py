import asyncio
import hashlib
import json
import secrets
from contextlib import suppress
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from .service import SudokuVibeError, SudokuVibeService
from .storage import SudokuVibeStorage


class SudokuVibeConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    request_routes = {
        "get_board_data": ("board_data", False),
        "set_value": ("set_value", True),
        "set_context": ("context_data", False),
        "generate_board": ("board_data", True),
    }

    async def connect(self) -> None:
        self.group_joined = False
        self.presence_acquired = False
        self.presence_task = None
        session = self.scope.get("session", {})
        lobby = session.get("room_code")
        if not isinstance(lobby, str) or not lobby:
            # Complete the handshake so browsers receive the application close
            # code instead of an HTTP 403 reported as an opaque 1006 error.
            await self.accept()
            await self.close(code=4401)
            return

        username = session.get(
            "sudoku_vibe_username",
            self.scope.get("cookies", {}).get("nick", "undefined"),
        )
        if not isinstance(username, str) or not username:
            username = "undefined"

        self.lobby = lobby
        self.username = username
        lobby_digest = hashlib.sha256(lobby.encode()).hexdigest()
        self.group_name = f"sudoku_vibe_{lobby_digest}"
        self.connection_id = secrets.token_urlsafe(32)
        self.storage = SudokuVibeStorage()
        self.presence_acquired = await self.storage.acquire_presence(
            lobby,
            username,
            self.connection_id,
        )
        if not self.presence_acquired:
            await self.accept()
            await self.close(code=4409)
            return

        self.service = SudokuVibeService(
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

        try:
            response_data = await handler(data)
        except SudokuVibeError as error:
            if error.code == "connection_replaced":
                await self.close(code=4409)
            else:
                await self.send_error(error.code, error.message)
            return

        message = {"kind": response_kind, "data": response_data}
        await self.send(text_data=json.dumps(message))
        if broadcast:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "forward_message",
                    "sender": self.channel_name,
                    "message": message,
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
        await self.send(text_data=json.dumps(event["message"]))

    async def send_error(self, code: str, message: str) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "kind": "error",
                    "data": {"code": code, "message": message},
                }
            )
        )
