"""Static definitions only. No database, Redis or static-storage calls."""
BOARD_SIDE = 9
BOARD_CELL_COUNT = 81
DEFAULT_ALLOWED_VALUES = ("", *range(1, BOARD_SIDE + 1))
SUPPORTED_SIZES = (9, 16)


def allowed_values(size: int = BOARD_SIDE) -> list[int | str]:
    return ["", *range(1, size + 1)]

BONUS_DEFINITIONS = (
    ("SWAP", "Перестановка", "⇄"), ("ROLL", "Поворот", "↻"),
    ("SHADOW_BOX", "Тень", "◧"), ("DANCE", "Танец", "♫"),
    ("GRAYSCALE", "Без цвета", "◐"), ("PULSE", "Пульсация", "◌"),
)
EFFECT_DEFAULTS = {
    'SHADOW_BOX': {'blurPx': 6}, 'ROLL': {'periodMs': 4000},
    'DANCE': {'angleDegrees': 3, 'periodMs': 800}, 'GRAYSCALE': {'amount': 1},
    'PULSE': {'minOpacity': .35, 'periodMs': 1500},
}
SYMBOL_PRESET_DEFINITIONS = (
    ("plain", "Обычные цифры", None),
    ("ink", "Чернильные цифры", "sudoku_v2/img/digits.svg"),
    ("tokens", "Фишки", "sudoku_v2/img/tokens.svg"),
)
