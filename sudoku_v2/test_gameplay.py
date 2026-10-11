from copy import deepcopy
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase, TransactionTestCase

from game.models import Difficulty, SudokuBoard, SudokuCell
from .service import SudokuV2Service, SudokuV2Error


def make_stored_board():
    solution = {str(r * 9 + c): (r * 3 + r // 3 + c) % 9 + 1
                for r in range(9) for c in range(9)}
    return {"public": {
        "name": "Иван", "generationId": "A", "revision": 1, "size": 9,
        "difficulty": "medium", "values": dict(solution),
        "fixedCells": list(range(2, 81)), "bonuses": {"0": "ROLL"},
        "wrongCells": [], "startedAt": 1000, "finishedAt": None,
        "completed": False, "requiresGeneration": False,
    }, "solution": solution}


CATALOG = {"difficulties": [{"value": "medium", "label": "Средняя"}],
           "sizes": [9], "bonuses": [],
           "symbolPresets": [{"id": "plain", "label": "Цифры", "imageUrl": None}]}


class GameplayTests(SimpleTestCase):
    def test_digit_limit_counts_all_values_and_erase_restores_capacity(self):
        board = make_stored_board()
        board["public"]["fixedCells"] = [1]
        board["public"]["values"] = {str(i): 1 if i < 8 else "" for i in range(81)}
        board["public"]["wrongCells"] = [2, 3]
        ninth = SudokuV2Service.apply_value(board, 8, 1, 2000)
        with self.assertRaises(SudokuV2Error) as error:
            SudokuV2Service.apply_value(ninth, 9, 1, 3000)
        self.assertEqual(error.exception.code, "digit_limit_reached")
        erased = SudokuV2Service.apply_value(ninth, 0, "", 4000)
        restored = SudokuV2Service.apply_value(erased, 9, 1, 5000)
        self.assertEqual(sum(v == 1 for v in restored["public"]["values"].values()), 9)

    def test_digit_first_preference_is_validated_and_preserved(self):
        from .user_context import normalize_context
        self.assertFalse(normalize_context({}, "Иван", CATALOG)["preferences"]["digitFirstMode"])
        context = normalize_context({"preferences": {"digitFirstMode": True}}, "Иван", CATALOG)
        self.assertTrue(context["preferences"]["digitFirstMode"])
        with self.assertRaises(ValueError):
            normalize_context({"preferences": {"digitFirstMode": 1}}, "Иван", CATALOG)

    def test_wrong_full_board_and_finish_once(self):
        # A full incorrect permutation uses nine of each digit. Erase before fixing.
        board = make_stored_board()
        board["public"]["values"].update({"0": 2, "1": 1})
        wrong = SudokuV2Service.apply_value(board, 0, 2, 9000)
        self.assertEqual(wrong["public"]["wrongCells"], [0, 1])
        self.assertFalse(wrong["public"]["completed"])
        self.assertIsNone(wrong["public"]["finishedAt"])
        erased = SudokuV2Service.apply_value(wrong, 1, "", 9500)
        fixed = SudokuV2Service.apply_value(erased, 0, 1, 9700)
        done = SudokuV2Service.apply_value(fixed, 1, 2, 10000)
        self.assertTrue(done["public"]["completed"])
        self.assertEqual(done["public"]["finishedAt"], 10000)
        self.assertEqual(done["public"]["bonuses"], {"0": "ROLL"})
        with self.assertRaises(SudokuV2Error) as error:
            SudokuV2Service.apply_value(done, 0, "", 11000)
        self.assertEqual(error.exception.code, "board_completed")

    def test_fixed_and_erase(self):
        board = make_stored_board()
        with self.assertRaises(SudokuV2Error):
            SudokuV2Service.apply_value(board, 2, "", 2000)
        erased = SudokuV2Service.apply_value(board, 0, "", 3000)
        self.assertEqual(erased["public"]["wrongCells"], [])
        self.assertFalse(erased["public"]["completed"])
        self.assertEqual(erased["public"]["bonuses"], {"0": "ROLL"})

    async def test_stale_generation_and_replaced_connection(self):
        storage = AsyncMock()
        storage.get_context.return_value = {"allowedValues": [1, 2]}
        storage.get_board_state.return_value = make_stored_board()
        service = SudokuV2Service("room", "Иван", storage, "lease")
        data = {"boardName": "Иван", "generationId": "old", "cellIndex": 0, "value": 1}
        with self.assertRaises(SudokuV2Error) as error:
            await service.set_value(data)
        self.assertEqual(error.exception.code, "stale_generation")
        storage.save_board_state.assert_not_awaited()
        storage.save_board_state.return_value = "replaced"
        with self.assertRaises(SudokuV2Error) as error:
            await service.set_value({**data, "generationId": "A"})
        self.assertEqual(error.exception.code, "connection_replaced")
        self.assertTrue(await service.valid_value(""))

    async def test_private_solution_and_own_context(self):
        storage = AsyncMock()
        storage.get_context.return_value = None
        storage.get_active_usernames.return_value = {"Соперник"}
        storage.get_board_state.side_effect = lambda lobby, name: make_stored_board() if name == "Иван" else None
        service = SudokuV2Service("room", "Иван", storage, "lease")
        with patch.object(service, "get_catalog", AsyncMock(return_value=CATALOG)):
            result = await service.get_board_data({})
        self.assertNotIn("solution", str(result))
        self.assertEqual(len(result["boards"]), 2)
        self.assertEqual(result["config"]["username"], "Иван")

    async def test_context_allowlist(self):
        storage = AsyncMock()
        storage.save_context.return_value = True
        service = SudokuV2Service("room", "Иван", storage, "lease")
        with patch.object(service, "get_catalog", AsyncMock(return_value=CATALOG)):
            result = await service.set_context({"username": "Другой", "preferences": {"showErrors": True}})
            self.assertEqual(result["config"]["username"], "Иван")
            self.assertTrue(result["config"]["preferences"]["showErrors"])
            for data in ({"notes": {}}, {"preferences": {"finishedAt": 1}}, {"allowedValues": [True]}):
                with self.assertRaises(SudokuV2Error):
                    await service.set_context(data)

    async def test_zero_is_removed_from_legacy_context_and_rejected_as_move(self):
        from .user_context import normalize_context
        context = normalize_context({"allowedValues": ["", 0, 1, 9]}, "Иван", CATALOG)
        self.assertEqual(context["allowedValues"], ["", 1, 9])
        self.assertNotIn(0, normalize_context({}, "Иван", CATALOG)["allowedValues"])
        storage = AsyncMock()
        storage.get_context.return_value = {"allowedValues": [0, 1, 9]}
        service = SudokuV2Service("r", "Иван", storage, "lease")
        with self.assertRaises(SudokuV2Error) as error:
            await service.set_value({"boardName": "Иван", "generationId": "A", "cellIndex": 0, "value": 0})
        self.assertEqual(error.exception.code, "invalid_value")
        storage.save_board_state.assert_not_awaited()

    async def test_departed_boards_are_not_returned(self):
        storage = AsyncMock()
        storage.get_context.return_value = None
        storage.get_active_usernames.return_value = {"Иван", "Лена"}
        storage.get_board_state.return_value = None
        service = SudokuV2Service("r", "Иван", storage, "lease")
        with patch.object(service, "get_catalog", AsyncMock(return_value=CATALOG)):
            result = await service.get_board_data({})
        self.assertEqual({b["name"] for b in result["boards"]}, {"Иван", "Лена"})

    async def test_generation_revision_and_private_response(self):
        storage = AsyncMock()
        storage.get_board_state.return_value = make_stored_board()
        storage.save_board_state.return_value = "saved"
        service = SudokuV2Service("room", "Иван", storage, "lease")
        generated = make_stored_board()
        generated["public"]["values"]["0"] = ""
        with patch.object(service, "get_random_board", AsyncMock(return_value=generated)):
            result = await service.generate_board({"difficulty": "medium", "size": 9})
        self.assertNotIn("config", result)
        self.assertNotIn("solution", str(result))
        self.assertEqual(result["board"]["revision"], 2)
        self.assertNotEqual(result["board"]["generationId"], "A")
        self.assertEqual(set(result["board"]["bonuses"]), {"0", "1"})


class CatalogTests(TransactionTestCase):
    async def test_generation_uses_database_values_and_empty_flags(self):
        difficulty = await Difficulty.objects.acreate(name="easy", top_limit=30)
        board = await SudokuBoard.objects.acreate(difficulty=difficulty)
        solution = make_stored_board()["solution"]
        fixed = {0, 4, 8, 10, 18, 28, 40, 50, 60, 70, 80}
        await SudokuCell.objects.abulk_create([
            SudokuCell(board=board, number=i, value=solution[str(i)], is_empty=i not in fixed)
            for i in range(81)
        ])
        generated = await SudokuV2Service.get_random_board("easy", 9)
        self.assertEqual(set(generated["public"]["fixedCells"]), fixed)
        self.assertEqual(generated["solution"], solution)
        self.assertEqual(generated["public"]["values"],
                         {str(i): solution[str(i)] if i in fixed else "" for i in range(81)})

    async def test_catalog_reflects_database_changes(self):
        await Difficulty.objects.acreate(name="medium", top_limit=55)
        catalog = await SudokuV2Service.get_catalog()
        self.assertEqual(catalog["difficulties"], [{"value": "medium", "label": "Средняя"}])
        catalog["bonuses"].clear()
        await Difficulty.objects.acreate(name="easy", top_limit=30)
        updated = await SudokuV2Service.get_catalog()
        self.assertEqual(updated["difficulties"][0]["value"], "easy")
        self.assertEqual(len(updated["bonuses"]), 4)
