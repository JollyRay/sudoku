from typing import Any
from .constants import DEFAULT_ALLOWED_VALUES


def valid_board_value(value: Any) -> bool:
    return value == "" or (type(value) is int and 1 <= value <= 9)


def normalize_context(data: dict[str, Any], username: str, catalog: dict[str, Any]) -> dict[str, Any]:
    if set(data) - {"username", "allowedValues", "preferences"}:
        raise ValueError("Unknown context field")
    allowed = data.get("allowedValues", list(DEFAULT_ALLOWED_VALUES))
    if isinstance(allowed, list):
        # Migrate the previous default without discarding the other preferences.
        allowed = [v for v in allowed if not (type(v) is int and v == 0)]
    if not isinstance(allowed, list) or not all(valid_board_value(v) for v in allowed):
        raise ValueError("Invalid allowedValues")
    difficulties = [item["value"] for item in catalog["difficulties"]]
    default_difficulty = "medium" if "medium" in difficulties else next(iter(difficulties), None)
    preferences = {
        "difficulty": default_difficulty, "size": 9, "notesMode": False, "digitFirstMode": False,
        "showErrors": False, "symbolPresetId": "plain", "selectedOpponent": None,
        "twitchChannel": "",
    }
    supplied = data.get("preferences", {})
    if not isinstance(supplied, dict) or set(supplied) - set(preferences):
        raise ValueError("Invalid preferences")
    preferences.update(supplied)
    for key in ("notesMode", "showErrors", "digitFirstMode"):
        if type(preferences[key]) is not bool:
            raise ValueError(f"Invalid {key}")
    if type(preferences["size"]) is not int or preferences["size"] != 9:
        raise ValueError("Unsupported size")
    for key in ("twitchChannel", "selectedOpponent"):
        value = preferences[key]
        if key == "selectedOpponent" and value is None:
            continue
        if not isinstance(value, str) or len(value) > (100 if key == "twitchChannel" else 32):
            raise ValueError(f"Invalid {key}")
    if preferences["difficulty"] not in difficulties:
        preferences["difficulty"] = default_difficulty
    if preferences["symbolPresetId"] not in [p["id"] for p in catalog["symbolPresets"]]:
        preferences["symbolPresetId"] = "plain"
    return {"username": username, "allowedValues": list(dict.fromkeys(allowed)), "preferences": preferences}
