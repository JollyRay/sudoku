from typing import TypedDict

class MemberNick(TypedDict):
    nick: str

class OfferData(TypedDict):
    type: str
    sender: str
    data: dict[str, str]