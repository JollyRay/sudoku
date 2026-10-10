import hashlib
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore[import-untyped]
from django.db import IntegrityError

from game.models import LobbySetting, UserSetting

from .service import SudokuVibeError, SudokuVibeService


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
        "generate_board": RequestRoute("generate_board", "board_data"),
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

        lobby_setting, _ = await LobbySetting.objects.aget_or_create(code=lobby)
        try:
            user_setting = await UserSetting.objects.acreate(
                lobby=lobby_setting,
                nick=username,
            )
        except IntegrityError:
            await self.close(code=4409)
            return

        self.user_setting_id = user_setting.pk

        self.service = SudokuVibeService(lobby, username)
        lobby_digest = hashlib.sha256(lobby.encode()).hexdigest()
        self.group_name = f"sudoku_vibe_{lobby_digest}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        group_name = getattr(self, "group_name", None)
        if group_name is not None:
            await self.channel_layer.group_discard(group_name, self.channel_name)

        user_setting_id = getattr(self, "user_setting_id", None)
        if user_setting_id is not None:
            await UserSetting.objects.filter(pk=user_setting_id).adelete()

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
        handler: Callable[
            [dict[str, Any]],
            Awaitable[dict[str, Any] | None],
        ] = getattr(self.service, route.service_method)

        try:
            response_data = await handler(data)
        except SudokuVibeError as error:
            await self.send_error(error.code, error.message)
            return

        if route.response_kind is None or response_data is None:
            return

        message = {"kind": route.response_kind, "data": response_data}
        if route.broadcast:
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
