from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core.handlers.asgi import ASGIHandler
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from .consumers import SudokuVibeConsumer


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
class SudokuVibeLoginTests(SimpleTestCase):
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
                self.assertEqual(lobby.context["board_name"], username)
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
        self.assertEqual(lobby.context["board_name"], username)
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
        storage.get_lobby_state.return_value = (None, {})
        storage.get_active_usernames.return_value = set()
        storage.get_fixed_cells.return_value = set()

        with patch("sudoku_vibe.consumers.SudokuVibeStorage", return_value=storage):
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
