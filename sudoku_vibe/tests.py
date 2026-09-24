from django.test import SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django.templatetags.static import static

from .views import index


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage"
)
class SudokuVibeRoutingTests(SimpleTestCase):
    def test_lobby_route_is_connected(self) -> None:
        url = reverse("sudoku_vibe:lobby")

        self.assertEqual(url, "/sudoku-vibe/lobby")
        self.assertIs(resolve(url).func, index)

    def test_lobby_renders_component_entry_point(self) -> None:
        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sudoku Vibe")

    def test_lobby_renders_static_nine_by_nine_board(self) -> None:
        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertContains(response, 'class="sudoku-board"', count=1)
        self.assertContains(response, "data-row-index=", count=9)
        self.assertContains(response, "data-cell-index=", count=81)

    def test_board_uses_nick_cookie_as_its_name(self) -> None:
        self.client.cookies["nick"] = "player-one"

        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertEqual(response.context["board_name"], "player-one")
        self.assertContains(response, 'data-board-name="player-one"')
        self.assertContains(response, "<caption>player-one</caption>", html=True)

    def test_board_name_is_undefined_without_nick_cookie(self) -> None:
        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertEqual(response.context["board_name"], "undefined")
        self.assertContains(response, 'data-board-name="undefined"')

    def test_lobby_loads_empty_stylesheet_and_script(self) -> None:
        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertContains(response, static("sudoku_vibe/css/sudoku.css"))
        self.assertContains(response, static("sudoku_vibe/js/sudoku.js"))
