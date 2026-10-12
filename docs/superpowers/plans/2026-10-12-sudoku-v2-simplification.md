# SudokuV2: упрощение без изменения поведения

> Основной агент реализует; после каждого этапа свежая Astra 6 запускает проверки
> и `find-bugs`. Исправления перепроверяются до следующего этапа. Пользователь
> уже разрешил выполнение; дополнительное согласование плана не требуется.

**Goal:** убрать ненужные связи и дублирование, сделать ветвления читаемыми.
**Architecture:** сохранить текущие границы транзакций, протоколы, порядок await,
таймеры и публичные методы. Извлекать только действительно общие операции.
**Tech Stack:** существующие Python/Django/Redis, vanilla JS и node:test.
**Spec:** запрос пользователя и `docs/sudoku-v2-review-guide.md`.

## Ограничения и проверки

- Никаких новых библиотек приложения, миграций и изменений игрового поведения.
- Работать в текущей `codex/sudoku-v2`; baseline `c9a8837`.
- Реальный Twitch и production не запускать. Redis тестов: localhost16379/15.
- Новые проверки только для существенных пробелов покрытия; существующие проверки
  поведения сохранять. Для чистого форматирования дополнительно сравнивать AST.
- Не менять правила fallback, порядок побочных эффектов и очистки ресурсов.
- Отделение Twitch façade было условной рекомендацией на будущее; дополнительные
  делегирующие обёртки сейчас не устраняют дублирование, поэтому не добавляются.

## Этапы

### 1. Серверный context и неиспользуемая обёртка

Files: `sudoku_v2/service.py`, `tests/sudoku_v2/test_gameplay.py`.
Общий async `_restore_context(context, size, *, catalog=None, reset_values=False)`:
allowlist старых данных, прежний fallback и прежние моменты чтения каталога.
Удалить неиспользуемый `SudokuV2Service.valid_cell_index`, сохранив функцию validator.
- [ ] Зафиксировать проверки старого context: приватные поля, invalid preferences,
  сохранение allowedValues при чтении и сброс при генерации9/16.
- [ ] Извлечь helper и удалить обёртку, не трогая CAS и ошибки set_context.
- [ ] Python suite, check; независимая Astra/find-bugs; исправления; отдельный commit.

### 2. Общие тестовые данные и окружение

Files: `tests/sudoku_v2/support.py`, существующие Python-тесты SudokuV2.
Fixtures `CATALOG`, `make_stored_board`, `sized_board`; mixins для Redis/бонусов/
Twitch setup; FakeWriter/eventually. Support не наследует TestCase и не содержит
test-методов. Тесты больше не импортируют другие test-модули.
- [ ] Зафиксировать test IDs и тела test-методов до изменений.
- [ ] Перенести helpers/setup с сохранением порядка setup/cleanup и значений.
- [ ] Сверить discovery, выполнить весь Python suite; Astra/find-bugs; commit.

### 3. Читаемость Python Twitch

Files: `sudoku_v2/twitch/{commands,registry,service,irc,worker,types}.py`.
- [ ] Развернуть однострочные compound statements, semicolon statements и
  вложенные тернарные ветви; сохранить порядок await и прежние исключения.
- [ ] Проверить AST для чистых преобразований; Python suite/check;
  независимая Astra/find-bugs; исправления; commit.

### 4. Обработчики DOM и читаемость клиента

Files: `sudoku_v2/static/sudoku_v2/js/{events,ui,twitch,state,network,effects,layout,
board,input,geometry,config,local-context}.js`, связанные JS-тесты.
`createEventBindings()` возвращает `{bind(target,event,handler),dispose()}`;
три UI-монтажа используют один helper, каждый со своим набором подписок.
- [ ] Проверить независимость групп обработчиков и снятие обработчиков.
- [ ] Убрать три копии bind/cleanup, развернуть сложные ветвления и цепочки действий;
  простые getters не дробить, новые абстрактные контроллеры не вводить.
- [ ] Node suite, Python suite/check; AST сравнение форматирования и браузерный
  smoke при изменении DOM lifecycle; свежая Astra/find-bugs; исправления; commit.
- [ ] Кратко обновить обзор: что применено, что осталось условной рекомендацией,
  фактически выполненные проверки. Итоговый review охватывает все четыре этапа.
