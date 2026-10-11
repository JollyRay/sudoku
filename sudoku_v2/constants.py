"""Static definitions only. No database, Redis or static-storage calls."""
BOARD_SIDE = 9
BOARD_CELL_COUNT = 81
DEFAULT_ALLOWED_VALUES = ("", *range(1, BOARD_SIDE + 1))
SUPPORTED_SIZES = (9,)
BONUS_DEFINITIONS = (
    ("SWAP", "Перестановка", "⇄"), ("ROLL", "Поворот", "↻"),
    ("SHADOW_BOX", "Тень", "◧"), ("DANCE", "Танец", "♫"),
)
SYMBOL_PRESET_DEFINITIONS = (
    ("plain", "Обычные цифры", None),
    ("ink", "Чернильные цифры", "sudoku_v2/img/digits.svg"),
    ("tokens", "Фишки", "sudoku_v2/img/tokens.svg"),
)
