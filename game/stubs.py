from typing import TypedDict


class BonusCellDict(TypedDict):
    bonus_name: str
    cell__number: int

class BorderIdDict(TypedDict):
    id: int

class UserInLobbyInfo(TypedDict):
    value: dict[str, int] | None
    bonus: dict[str, str] | None
    static_answer: list[int] | None
    wrong_answer: list[int]
    time_from: int | None
    time_to: int | None
