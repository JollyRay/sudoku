from typing import TypedDict

class MemberNick(TypedDict):
    nick: str
    has_screen_sream: bool

class OfferUserData(TypedDict):
    sdpVoice: str|None
    sdpScreenReceiver: str|None
    sdpScreenProvider: str|None

class OfferData(TypedDict):
    type: str
    sender: str
    data: dict[str, OfferUserData]
