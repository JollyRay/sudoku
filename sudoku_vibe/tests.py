from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core.handlers.asgi import ASGIHandler
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from .consumers import SudokuVibeConsumer
from .service import SudokuVibeError


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
class SudokuVibeLoginTests(SimpleTestCase):
    async def test_replaced_connection_closes_without_an_error_message(self) -> None:
        for renewed in (False, True):
            with self.subTest(replaced_during_write=renewed):
                storage = AsyncMock()
                storage.PRESENCE_EXPIRY_SECONDS = 90
                storage.acquire_presence.return_value = True
                storage.renew_presence.return_value = renewed
                service = AsyncMock()
                service.set_value.side_effect = SudokuVibeError("connection_replaced")
                with patch("sudoku_vibe.consumers.SudokuVibeStorage", return_value=storage), patch(
                    "sudoku_vibe.consumers.SudokuVibeService", return_value=service
                ):
                    websocket = WebsocketCommunicator(SudokuVibeConsumer.as_asgi(), "/ws/sudoku-vibe/")
                    websocket.scope["session"] = {"room_code": "test-room", "sudoku_vibe_username": "Иван"}
                    connected, _ = await websocket.connect()
                    self.assertTrue(connected)
                    await websocket.send_json_to({"kind": "set_value", "data": {}})
                    self.assertEqual(await websocket.receive_output(), {"type": "websocket.close", "code": 4409})
                    await websocket.disconnect()

    async def test_rejection_sends_browser_visible_close_code(self) -> None:
        for session, code in (
            ({}, 4401),
            ({"room_code": "test-room", "sudoku_vibe_username": "Иван"}, 4409),
        ):
            with self.subTest(code=code):
                storage = AsyncMock()
                storage.acquire_presence.return_value = False
                with patch("sudoku_vibe.consumers.SudokuVibeStorage", return_value=storage):
                    websocket = WebsocketCommunicator(
                        SudokuVibeConsumer.as_asgi(), "/ws/sudoku-vibe/"
                    )
                    websocket.scope["session"] = session
                    connected, _ = await websocket.connect()
                    self.assertTrue(connected)
                    self.assertEqual(await websocket.receive_output(),
                                     {"type": "websocket.close", "code": code})
                    await websocket.disconnect()
                    storage.release_presence.assert_not_awaited()

    def test_login_preserves_name_through_http_and_websocket(self) -> None:
        for username in ("Иван", "Игрок 🧩", "Alice", "player%20name"):
            with self.subTest(username=username):
                self.client.cookies["nick"] = "previous-player"
                with patch(
                    "sudoku_vibe.forms.SudokuVibeStorage.is_username_active",
                    return_value=False,
                ) as is_active:
                    response = self.client.post(
                        reverse("sudoku_vibe:join"),
                        {"username": username, "room_name": "test-room"},
                    )

                self.assertEqual(response.status_code, 302)
                is_active.assert_called_once_with("test-room", username)
                # The test client alone does not serialize Set-Cookie as ASGI does.
                async_to_sync(ASGIHandler().send_response)(response, AsyncMock())

                lobby = self.client.get(reverse("sudoku_vibe:lobby"))
                self.assertEqual(lobby.context["bootstrap"]["username"], username)
                form = self.client.get(reverse("sudoku_vibe:join"))
                self.assertEqual(form.context["form"].initial["username"], username)
                async_to_sync(self.assert_websocket_username)(username)

    def test_existing_nick_cookie_remains_supported(self) -> None:
        username = "legacy%20name"
        self.client.cookies["nick"] = username
        session = self.client.session
        session["room_code"] = "test-room"
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        lobby = self.client.get(reverse("sudoku_vibe:lobby"))
        self.assertEqual(lobby.context["bootstrap"]["username"], username)
        form = self.client.get(reverse("sudoku_vibe:join"))
        self.assertEqual(form.context["form"].initial["username"], username)
        async_to_sync(self.assert_websocket_username)(username)

    async def assert_websocket_username(self, username: str) -> None:
        cookie_header = "; ".join(
            f"{name}={cookie.coded_value}"
            for name, cookie in self.client.cookies.items()
        ).encode("ascii")
        storage = AsyncMock()
        storage.PRESENCE_EXPIRY_SECONDS = 90
        storage.acquire_presence.return_value = True
        storage.renew_presence.return_value = True
        storage.get_active_usernames.return_value = set()
        storage.get_board_state.return_value = None
        storage.get_context.return_value = None

        from .test_gameplay import CATALOG
        with patch("sudoku_vibe.consumers.SudokuVibeStorage", return_value=storage), patch(
            "sudoku_vibe.service.SudokuVibeService.get_catalog", AsyncMock(return_value=CATALOG)
        ):
            websocket = WebsocketCommunicator(
                AuthMiddlewareStack(SudokuVibeConsumer.as_asgi()),
                "/ws/sudoku-vibe/",
                headers=[(b"cookie", cookie_header)],
            )
            connected, _ = await websocket.connect()
            self.assertTrue(connected)
            try:
                await websocket.send_json_to({"kind": "get_board_data", "data": {}})
                message = await websocket.receive_json_from()
                self.assertEqual(message["kind"], "board_data")
                self.assertEqual(message["data"]["board"]["name"], username)
                self.assertEqual(message["data"]["config"]["username"], username)
                self.assertEqual(
                    storage.acquire_presence.call_args.args[:2],
                    ("test-room", username),
                )
            finally:
                await websocket.disconnect()
