import asyncio
import hashlib
import json
import secrets
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]

from .service import SudokuVibeError, SudokuVibeService
from .storage import SudokuVibeStorage


@dataclass(frozen=True)
class RequestRoute:
    service_method: str
    response_kind: str | None
    broadcast: bool = False


class SudokuVibeConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    request_routes = {
        "get_board_data": RequestRoute("get_board_data", "board_data"),
        "set_value": RequestRoute("set_value", "set_value", broadcast=True),
        "set_context": RequestRoute("set_context", None),
        "generate_board": RequestRoute(
            "generate_board",
            "board_data",
            broadcast=True,
        ),
    }

    async def connect(self) -> None:
        session = self.scope.get("session", {})
        lobby = session.get("room_code")
        if not isinstance(lobby, str) or not lobby:
            await self.close(code=4401)
            return

        username = self.scope.get("cookies", {}).get("nick", "undefined")
        if not isinstance(username, str) or not username:
            username = "undefined"

        self.lobby = lobby
        self.username = username
        self.connection_id = secrets.token_urlsafe(32)
        self.storage = SudokuVibeStorage()
        self.presence_acquired = await self.storage.acquire_presence(
            lobby,
            username,
            self.connection_id,
        )
        if not self.presence_acquired:
            await self.close(code=4409)
            return

        self.service = SudokuVibeService(
            lobby,
            username,
            self.storage,
            self.connection_id,
        )
        lobby_digest = hashlib.sha256(lobby.encode()).hexdigest()
        self.group_name = f"sudoku_vibe_{lobby_digest}"

        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.group_joined = True
            await self.accept()
        except BaseException:
            if getattr(self, "group_joined", False):
                with suppress(Exception):
                    await self.channel_layer.group_discard(
                        self.group_name,
                        self.channel_name,
                    )
            await self.release_presence()
            raise

        self.presence_task = asyncio.create_task(self.keep_presence_alive())

    async def disconnect(self, close_code: int) -> None:
        presence_task = getattr(self, "presence_task", None)
        if presence_task is not None:
            presence_task.cancel()
            with suppress(asyncio.CancelledError):
                await presence_task

        try:
            if getattr(self, "group_joined", False):
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
        if not getattr(self, "presence_acquired", False):
            return

        try:
            await self.storage.release_presence(
                self.lobby,
                self.username,
                self.connection_id,
            )
        finally:
            self.presence_acquired = False

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        if text_data is None:
            await self.send_error("invalid_message", "Text JSON is required")
            return

        try:
            envelope = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("invalid_json", "Message must be valid JSON")
            return

        if not isinstance(envelope, dict):
            await self.send_error("invalid_message", "Message must be an object")
            return

        kind = envelope.get("kind")
        data = envelope.get("data", {})
        if not isinstance(kind, str) or not isinstance(data, dict):
            await self.send_error("invalid_message", "Invalid kind or data")
            return

        route = self.request_routes.get(kind)
        if route is None:
            await self.send_error("invalid_message", "Unknown message kind")
            return

        await self.dispatch_request(route, data)

    async def dispatch_request(
        self,
        route: RequestRoute,
        data: dict[str, Any],
    ) -> None:
        if not await self.ensure_current_presence():
            return

        handler: Callable[
            [dict[str, Any]],
            Awaitable[dict[str, Any] | None],
        ] = getattr(self.service, route.service_method)

        try:
            response_data = await handler(data)
        except SudokuVibeError as error:
            await self.send_error(error.code, error.message)
            if error.code == "connection_replaced":
                await self.close(code=4409)
            return

        if route.response_kind is None or response_data is None:
            return

        message = {"kind": route.response_kind, "data": response_data}
        if route.broadcast:
            await self.send(text_data=json.dumps(message))
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "forward_message",
                    "sender": self.channel_name,
                    "message": message,
                },
            )
            return

        await self.send(text_data=json.dumps(message))

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
                "Unable to verify connection ownership",
            )
            await self.close(code=1011)
            return False

        if renewed:
            return True

        await self.send_error(
            "connection_replaced",
            "This user is connected from another client",
        )
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
