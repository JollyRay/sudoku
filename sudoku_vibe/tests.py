from django.test import SimpleTestCase
from django.urls import resolve, reverse

from .views import index


class SudokuVibeRoutingTests(SimpleTestCase):
    def test_lobby_route_is_connected(self) -> None:
        url = reverse("sudoku_vibe:lobby")

        self.assertEqual(url, "/sudoku-vibe/lobby")
        self.assertIs(resolve(url).func, index)

    def test_lobby_renders_component_entry_point(self) -> None:
        response = self.client.get(reverse("sudoku_vibe:lobby"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sudoku Vibe")
