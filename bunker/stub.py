from typing import List, NotRequired, TypedDict


class ExtraParam(TypedDict):
    min_value: NotRequired[int]
    max_value: NotRequired[int]
    choices: NotRequired[List[str]]
