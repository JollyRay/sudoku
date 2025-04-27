from typing import TypedDict, TYPE_CHECKING
from django.forms import ModelForm
from django.views.generic import ListView

from .models import VoiceGroup

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


if TYPE_CHECKING:
    VoiceGroupForm = ModelForm[VoiceGroup]
    VoiceGroupListView = ListView[VoiceGroup]
else:
    VoiceGroupForm = ModelForm
    VoiceGroupListView = ListView