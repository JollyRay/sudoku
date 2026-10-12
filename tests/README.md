# Тесты SudokuV2

Тесты отделены от кода приложения. Перенос 12 октября 2026 не меняет проверяемое
поведение: 12 Python-модулей, 9 JavaScript-модулей, 108 Python- и 53 JS-проверки.

После уточнения целей Twitch: 115 Python- и 55 JS-проверок. Общие fixtures и настройка
Redis/Twitch находятся в `sudoku_v2/support.py`; этот модуль не содержит тестов.

```text
tests/
  settings.py         Изолированные Django settings: SQLite in-memory, безопасные AppConfig
  preview_settings.py Настройки браузерного preview с отдельными SQLite и Redis namespace
  sudoku_v2/          Игровой сервис, WebSocket, бонусы, Twitch, Redis и интеграция
  game/               Генератор 9/16 и команда fillSudoku
  js/sudoku_v2/       Клиентские state/input/render/effects/layout/Twitch
```

Из корня репозитория, используя существующее виртуальное окружение:

```powershell
$env:SUDOKU_V2_TEST_REDIS_URL = 'redis://127.0.0.1:6379/15'
.venv\Scripts\python.exe manage.py check --settings=tests.settings
.venv\Scripts\python.exe manage.py test tests --settings=tests.settings
node --test tests/js/sudoku_v2/*.test.mjs
```

Redis должен работать по указанному адресу. Redis-тесты используют уникальные
префиксы и удаляют только свои ключи. Без переменной окружения эти проверки
будут пропущены; такой запуск не является полным прогоном.

Отдельные группы:

```powershell
.venv\Scripts\python.exe manage.py test tests.game --settings=tests.settings
.venv\Scripts\python.exe manage.py test tests.sudoku_v2.test_twitch_worker --settings=tests.settings
node --test tests/js/sudoku_v2/context.test.mjs
```

`sudoku_v2.test_settings` заменён на `tests.settings`, `sudoku_v2.tests` — на
`tests.sudoku_v2.test_routes`, остальные Python-модули получили префикс `tests.`.
`sudoku_v2/tests_js/` перенесён в `tests/js/sudoku_v2/`.
Browser preview использует `tests.preview_settings`.
Проверки `tests.sudoku_v2.test_settings` запускают worker и генератор в отдельных
процессах с недоступными посторонними приложениями и запретом SQL при старте.
Существующие тесты других приложений, например `breach_protocol/tests.py`,
не входят в перенос SudokuV2 и запускаются отдельно.
